from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from django.core.cache import cache
from .serializers import SellerContextResponse, AdminUserStatusUpdateRequest

from .serializers import (
    # auth
    RegisterRequest, LoginRequest, RefreshRequest, ForgotPasswordRequest, ResetPasswordRequest,
    ChangeEmailRequest, ConfirmEmailChangeRequest, ConfirmRegistrationRequest, PublicUserResponse,
    # user
    UserSelfUpdateRequest, AvatarUploadRequest,
    UserAdminCreateRequest, UserAdminUpdateRequest, UserAdminResponse, UserAdminListResponse, UserResponse,
    # seller
    SellerProfilePublicResponse, SellerProfilePrivateResponse, SellerProfileAdminResponse,
    SellerProfileCreateRequest, SellerProfileUpdateRequest, SellerLogoUploadRequest, SellerBannerUploadRequest,
    # bank accounts
    SellerBankAccountOwnerResponse, SellerBankAccountAdminResponse,
    SellerBankAccountCreateRequest, SellerBankAccountUpdateRequest, SellerMembershipUpdateRoleRequest,
    SellerMembershipResponse, SellerMembershipCreateRequest, ChangePasswordRequest,
)
from .services import commands, queries
from .services.exceptions import (
    EmailAlreadyUsed, InvalidCredentials, AccountNotActive,
    TokenInvalid, RefreshMissing, RefreshInvalid, RefreshNotRecognized
)
from .permissions import (
    IsAdmin, IsSelf, IsUserRoleOwner, IsSellerOwnerOrAdmin, IsBankAccountOwnerOrAdmin, IsSellerManagerOrOwner,
    IsMySellerOwnerOrAdmin  # noqa: F401 (część może być użyta później)
)
from .filters import UserFilter, UserCandidateFilter, SellerProfileFilter, SellerBankAccountFilter, SellerMembershipFilter
from .models import SellerProfile, SellerBankAccount

User = get_user_model()


# ===== Helpers: cookies =====

def set_refresh_cookie(resp: Response, refresh_jwt: str):
    resp.set_cookie(
        settings.AUTH_COOKIE_NAME,
        refresh_jwt,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        domain=settings.AUTH_COOKIE_DOMAIN or None,
        path=settings.AUTH_COOKIE_PATH,
    )


def clear_refresh_cookie(resp: Response):
    resp.delete_cookie(
        settings.AUTH_COOKIE_NAME,
        domain=settings.AUTH_COOKIE_DOMAIN or None,
        path=settings.AUTH_COOKIE_PATH,
    )


# ===== AUTH =====

class RegisterView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            data = commands.register_user(request, **ser.validated_data)
            return Response(data, status=201)
        except EmailAlreadyUsed as e:
            return Response({"detail": str(e)}, status=400)


class ConfirmRegistrationView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = ConfirmRegistrationRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            data = commands.confirm_registration(token=ser.validated_data["token"])
            return Response(data, status=200)
        except TokenInvalid as e:
            return Response({"detail": str(e)}, status=400)


class LoginView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            payload = commands.login_user(request, **ser.validated_data)
            resp = Response(payload, status=200)
            if settings.JWT_REFRESH_IN_COOKIE:
                set_refresh_cookie(resp, payload["refresh"])
            return resp
        except InvalidCredentials as e:
            return Response({"detail": str(e)}, status=401)
        except AccountNotActive as e:
            return Response({"detail": str(e)}, status=403)


class RefreshView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = RefreshRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            payload = commands.refresh_tokens(request, refresh_jwt=ser.validated_data.get("refresh"))
            resp = Response(payload, status=200)
            if settings.JWT_REFRESH_IN_COOKIE:
                set_refresh_cookie(resp, payload["refresh"])
            return resp
        except (RefreshMissing, RefreshInvalid, RefreshNotRecognized) as e:
            return Response({"detail": str(e)}, status=401)


class LogoutView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    def create(self, request, *args, **kwargs):
        commands.logout_user(request, user=request.user)
        resp = Response(status=204)
        if settings.JWT_REFRESH_IN_COOKIE:
            clear_refresh_cookie(resp)
        return resp


class ForgotPasswordView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = ForgotPasswordRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = commands.forgot_password(request, email=ser.validated_data["email"])
        return Response(data, status=200)


class ResetPasswordView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = ResetPasswordRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            data = commands.reset_password(**ser.validated_data)
            return Response(data, status=200)
        except TokenInvalid as e:
            return Response({"detail": str(e)}, status=400)


class ChangeEmailRequestView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = ChangeEmailRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            data = commands.request_email_change(request, user=request.user, new_email=ser.validated_data["new_email"])
            return Response(data, status=200)
        except EmailAlreadyUsed as e:
            return Response({"detail": str(e)}, status=400)


class ConfirmEmailChangeView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = ConfirmEmailChangeRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            data = commands.confirm_email_change(token=ser.validated_data["token"])
            return Response(data, status=200)
        except (TokenInvalid, EmailAlreadyUsed) as e:
            return Response({"detail": str(e)}, status=400)

class ChangePasswordView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = ChangePasswordRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            data = commands.change_password(user=request.user, **ser.validated_data)
            resp = Response(data, status=200)
            if settings.JWT_REFRESH_IN_COOKIE:
                clear_refresh_cookie(resp)
            return resp
        except InvalidCredentials as e:
            return Response({"detail": str(e)}, status=400)


# ===== USER – PUBLIC (pojedynczy) =====

class PublicUserViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = User.objects.all()
    lookup_field = "public_id"
    serializer_class = UserResponse


# ===== USER – SELF =====

class SelfUserViewSet(viewsets.ViewSet):
    """
    /api/users/me  [GET, PATCH]
    /api/users/me/avatar [POST, DELETE]
    """
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request):
        return Response(queries.me_payload(request.user), status=200)

    def partial_update(self, request):
        ser = UserSelfUpdateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        result = commands.update_user_self(user=request.user, **ser.validated_data)
        return Response(result, status=200)

    @action(detail=False, methods=["post"], url_path="avatar")
    def upload_avatar(self, request):
        ser = AvatarUploadRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        url = commands.upload_user_avatar(user=request.user, image=ser.validated_data["image"])
        return Response({"image_url": request.build_absolute_uri(url)}, status=200)

    @upload_avatar.mapping.delete
    def delete_avatar(self, request):
        commands.delete_user_avatar(user=request.user)
        return Response(status=204)


# ===== USER – ADMIN CRUD + LIST =====

class AdminUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    queryset = User.objects.all().order_by("-date_joined")
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter, SearchFilter)
    filterset_class = UserFilter
    search_fields = ("email", "first_name", "last_name")
    ordering_fields = ("date_joined", "email", "last_login")

    def get_serializer_class(self):
        if self.action in ("list",):
            return UserAdminListResponse
        elif self.action in ("create",):
            return UserAdminCreateRequest
        elif self.action in ("update", "partial_update"):
            return UserAdminUpdateRequest
        return UserAdminResponse

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            u = commands.admin_create_user(**ser.validated_data)
            return Response(UserAdminResponse(u).data, status=201)
        except EmailAlreadyUsed as e:
            return Response({"detail": str(e)}, status=400)

    def update(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        u = commands.admin_update_user(public_id=kwargs[self.lookup_field], **ser.validated_data)
        return Response(UserAdminResponse(u).data, status=200)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        commands.admin_delete_user(public_id=kwargs[self.lookup_field])
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, public_id=None):
        ser = AdminUserStatusUpdateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        u = commands.admin_set_user_status(public_id=public_id, **ser.validated_data)
        return Response(UserAdminResponse(u).data, status=200)


# ===== SELLER PROFILE – PUBLIC LIST/DETAIL =====

class PublicSellerProfileViewSet(mixins.ListModelMixin,
                                 mixins.RetrieveModelMixin,
                                 viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    # permission_classes = [IsAdmin]
    queryset = SellerProfile.objects.select_related("owner").all()
    lookup_field = "slug"
    filter_backends = (DjangoFilterBackend, OrderingFilter, SearchFilter)
    filterset_class = SellerProfileFilter
    search_fields = ("company_name", "slug")
    ordering_fields = ("rating", "followers_count", "company_name")
    serializer_class = SellerProfilePublicResponse


# ===== SELLER PROFILE - OWNER (create/own/detail/update + images) =====
class MySellerProfileViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if getattr(self, "action", None) == "retrieve":
            return [permissions.IsAuthenticated()]
        if getattr(self, "action", None) == "create":
            return [IsAdmin()]
        return [permissions.IsAuthenticated(), IsMySellerOwnerOrAdmin()]

    def retrieve(self, request):
        sp = (
            SellerProfile.objects
            .select_related("owner")
            .filter(owner=request.user)
            .first()
        )

        if not sp:
            mem = queries.best_membership_for_user(request.user)
            if mem:
                sp = mem.seller_profile

        if not sp:
            return Response({"detail": "Not found"}, status=404)

        return Response(SellerProfilePrivateResponse(sp).data, status=200)

    def create(self, request):
        if SellerProfile.objects.filter(owner=request.user).exists():
            return Response({"detail": "Seller profile already exists"}, status=400)
        ser = SellerProfileCreateRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        sp = commands.create_seller_for_owner(owner=request.user, data=ser.validated_data)
        return Response(SellerProfilePrivateResponse(sp).data, status=201)

    def partial_update(self, request):
        sp = SellerProfile.objects.filter(owner=request.user).first()
        if not sp:
            return Response({"detail": "Forbidden"}, status=403)
        ser = SellerProfileUpdateRequest(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        sp = commands.update_seller_owned(seller=sp, data=ser.validated_data)
        return Response(SellerProfilePrivateResponse(sp).data, status=200)

    @action(detail=False, methods=["post"], url_path="logo")
    def upload_logo(self, request):
        sp = SellerProfile.objects.filter(owner=request.user).first()
        if not sp:
            return Response({"detail": "Forbidden"}, status=403)
        ser = SellerLogoUploadRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        url = commands.upload_seller_logo(seller=sp, logo=ser.validated_data["logo"])
        return Response({"logo_url": request.build_absolute_uri(url)}, status=200)

    @upload_logo.mapping.delete
    def delete_logo(self, request):
        sp = SellerProfile.objects.filter(owner=request.user).first()
        if not sp:
            return Response({"detail": "Forbidden"}, status=403)
        commands.delete_seller_logo(seller=sp)
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="banner")
    def upload_banner(self, request):
        sp = SellerProfile.objects.filter(owner=request.user).first()
        if not sp:
            return Response({"detail": "Forbidden"}, status=403)
        ser = SellerBannerUploadRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        url = commands.upload_seller_banner(seller=sp, banner=ser.validated_data["banner"])
        return Response({"banner_url": request.build_absolute_uri(url)}, status=200)

    @upload_banner.mapping.delete
    def delete_banner(self, request):
        sp = SellerProfile.objects.filter(owner=request.user).first()
        if not sp:
            return Response({"detail": "Forbidden"}, status=403)
        commands.delete_seller_banner(seller=sp)
        return Response(status=204)


# ===== SELLER PROFILE – ADMIN CRUD =====

class AdminSellerProfileViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    queryset = SellerProfile.objects.select_related("owner").all().order_by("-created_at")
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter, SearchFilter)
    filterset_class = SellerProfileFilter
    search_fields = ("company_name", "slug", "owner__email")
    ordering_fields = ("rating", "followers_count", "company_name", "created_at")

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return SellerProfileAdminResponse
        elif self.action in ("create",):
            return SellerProfileCreateRequest
        return SellerProfileUpdateRequest

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        owner_id = request.data.get("owner_id")
        if not owner_id:
            return Response({"detail": "owner_id required"}, status=400)
        owner = get_object_or_404(User, id=owner_id)
        if SellerProfile.objects.filter(owner=owner).exists():
            return Response({"detail": "Owner already has seller profile"}, status=400)
        sp = SellerProfile(owner=owner, **ser.validated_data)
        sp.save()
        commands.ensure_owner_membership(sp)
        return Response(SellerProfileAdminResponse(sp).data, status=201)

    def update(self, request, *args, **kwargs):
        sp = get_object_or_404(SellerProfile, public_id=kwargs.get("public_id"))
        ser = self.get_serializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        commands.update_seller_owned(seller=sp, data=ser.validated_data)
        return Response(SellerProfileAdminResponse(sp).data, status=200)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


# ===== BANK ACCOUNTS =====
class MySellerBankAccountViewSet(viewsets.GenericViewSet,
                                 mixins.ListModelMixin,
                                 mixins.RetrieveModelMixin,
                                 mixins.CreateModelMixin,
                                 mixins.UpdateModelMixin,
                                 mixins.DestroyModelMixin):
    """
     /api/sellers/mine/bank-accounts/...
     - LIST/RETRIEVE: konta bankowe sklepów, których właścicielem jest zalogowany użytkownik.
     - CREATE: tworzy konto bankowe dla wskazanego sklepu pod warunkiem, że sklep należy do zalogowanego użytkownika.
     - UPDATE/DELETE/SET-DEFAULT: operacje na kontach bankowych należących do sklepu, którego właścicielem jest zalogowany użytkownik.
     """
    permission_classes = [permissions.IsAuthenticated, IsMySellerOwnerOrAdmin]
    lookup_field = "public_id"
    serializer_class = SellerBankAccountOwnerResponse
    filter_backends = (DjangoFilterBackend, OrderingFilter, SearchFilter)
    filterset_class = SellerBankAccountFilter
    ordering_fields = ("created_at", "is_default", "iban")
    search_fields = ("iban", "bank_name", "account_holder")

    def get_queryset(self):
        # tylko konta dla sklepu, którego właścicielem jest user
        return SellerBankAccount.objects.select_related("seller_profile").filter(
            seller_profile__owner=self.request.user
        ).order_by("-created_at")

    # def get_queryset(self):
    #     return queries.bank_accounts_for_user(self.request.user)

    def get_serializer_class(self):
        if self.action in ("create",):
            return SellerBankAccountCreateRequest
        if self.action in ("update", "partial_update"):
            return SellerBankAccountUpdateRequest
        return SellerBankAccountOwnerResponse

    # def create(self, request, *args, **kwargs):
    #     ser = self.get_serializer(data=request.data)
    #     ser.is_valid(raise_exception=True)
    #     seller_public_id = request.data.get("seller_public_id")
    #     if not seller_public_id:
    #         return Response({"detail": "seller_public_id required"}, status=400)
    #     acc = commands.member_create_bank_account(
    #         user=request.user,
    #         seller_public_id=seller_public_id,
    #         data=ser.validated_data
    #     )
    #     return Response(SellerBankAccountOwnerResponse(acc).data, status=201)

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        seller_public_id = request.data.get("seller_public_id")
        if not seller_public_id:
            return Response({"detail": "seller_public_id required"}, status=400)
        # twardy check: czy to mój sklep?
        seller = queries.get_seller_by_public_id(seller_public_id)
        if not seller or seller.owner_id != request.user.id:
            return Response({"detail": "Forbidden"}, status=403)
        acc = commands.admin_create_bank_account(seller_profile=seller, data=ser.validated_data)
        return Response(SellerBankAccountOwnerResponse(acc).data, status=201)

    def update(self, request, *args, **kwargs):
        public_id = kwargs.get("public_id")
        ser = self.get_serializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        acc = commands.member_update_bank_account(user=request.user, public_id=public_id, data=ser.validated_data)
        return Response(SellerBankAccountOwnerResponse(acc).data, status=200)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        public_id = kwargs.get("public_id")
        commands.member_delete_bank_account(user=request.user, public_id=public_id)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, public_id=None):
        acc = commands.member_set_default_bank_account(user=request.user, public_id=public_id)
        return Response({"message": "Ustawiono jako domyślne", "public_id": acc.public_id}, status=200)


# ===== BANK ACCOUNTS – ADMIN =====

class AdminSellerBankAccountViewSet(viewsets.ModelViewSet):
    """
    /api/sellers/mine/bank-accounts/...
    - LIST/RETRIEVE/CREATE/UPDATE/DELETE: tylko administrator (superuser).
    - CREATE wymaga w body: seller_public_id (ID własnego sklepu).
    """
    permission_classes = [IsAdmin]
    queryset = (
        SellerBankAccount.objects
        .select_related("seller_profile", "seller_profile__owner")
        .all()
        .order_by("-created_at")
    )
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter, SearchFilter)
    filterset_class = SellerBankAccountFilter
    ordering_fields = ("created_at", "is_default", "iban")
    search_fields = ("iban", "bank_name", "account_holder", "seller_profile__slug", "seller_profile__owner__email")

    def get_serializer_class(self):
        if self.action in ("create",):
            return SellerBankAccountCreateRequest
        if self.action in ("update", "partial_update"):
            return SellerBankAccountUpdateRequest
        return SellerBankAccountAdminResponse

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        seller_public_id = request.data.get("seller_public_id")
        if not seller_public_id:
            return Response({"detail": "seller_public_id required"}, status=400)
        seller = get_object_or_404(SellerProfile, public_id=seller_public_id)
        acc = commands.admin_create_bank_account(seller_profile=seller, data=ser.validated_data)
        return Response(SellerBankAccountAdminResponse(acc).data, status=201)

    def update(self, request, *args, **kwargs):
        public_id = kwargs.get("public_id")
        ser = self.get_serializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        acc = commands.admin_update_bank_account(public_id=public_id, data=ser.validated_data)
        return Response(SellerBankAccountAdminResponse(acc).data, status=200)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, public_id=None):
        acc = commands.admin_set_default_bank_account(public_id=public_id)
        return Response({"message": "Ustawiono jako domyślne", "public_id": acc.public_id}, status=200)

class SellerMembersViewSet(viewsets.GenericViewSet):
    """
    /api/sellers/<seller_public_id>/members [GET, POST]
    /api/sellers/<seller_public_id>/members/<member_public_id> [PATCH, DELETE]
    Paginacja, sortowanie i szukanie przez wbudowane backendy DRF.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SellerMembershipResponse
    filterset_class = SellerMembershipFilter
    search_fields = ("user__email","user__first_name","user__last_name","user__phone_number","user__public_id")
    ordering_fields = ("created_at", "role", "user__email")

    def _get_seller(self, seller_public_id: str):
        return queries.get_seller_by_public_id(seller_public_id)

    @action(detail=False, methods=["get"], url_path="candidates")
    def candidates(self, request, seller_public_id: str = None):
        seller = self._get_seller(seller_public_id)
        if not seller:
            return Response({"detail": "Not found"}, status=404)
        if not queries.can_manage_members(request.user, seller):
            return Response({"detail": "Forbidden"}, status=403)

        # --- twarde reguły biznesowe (nie-parametryzowalne) ---
        qs = (
            User.objects
            .filter(is_active=True)
            .exclude(role="CLIENT")
            .exclude(  # już-członkowie tego sklepu OUT
                seller_memberships__seller_profile=seller,
                seller_memberships__is_active=True
            )
            .order_by("email")
        )

        # domyślna rola = EMPLOYEE (jeśli nie podano)
        if "role" not in request.query_params:
            qs = qs.filter(role="EMPLOYEE")

        # --- parametry requestu przez FilterSet ---
        f = UserCandidateFilter(request.query_params, queryset=qs, request=request)
        qs = f.qs

        page = self.paginate_queryset(qs)
        data = [PublicUserResponse(u).data for u in (page or qs)]
        return self.get_paginated_response(data) if page is not None else Response(data, status=200)

    def list(self, request, seller_public_id: str = None):
        seller = self._get_seller(seller_public_id)
        if not seller:
            return Response({"detail": "Not found"}, status=404)
        if not queries.can_manage_members(request.user, seller):
            return Response({"detail": "Forbidden"}, status=403)

        # bazowy QS (aktywni członkowie, z sensownym sortem wg roli)
        qs = queries.members_for_seller(seller)

        # DRF-owe backendy: search/order wg query params (?search=..., ?ordering=...)
        qs = self.filter_queryset(qs)

        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data, status=200)


    def create(self, request, seller_public_id: str = None):
        seller = self._get_seller(seller_public_id)
        if not queries.can_manage_members(request.user, seller):
            return Response({"detail": "Forbidden"}, status=403)
        ser = SellerMembershipCreateRequest(data=request.data)
        ser.is_valid(raise_exception=True)

        # rozpoznaj użytkownika
        target = None
        if ser.validated_data.get("user_public_id"):
            target = queries.get_user_by_public_id(ser.validated_data["user_public_id"])  # jeśli masz helper w repo/queries
        if not target and ser.validated_data.get("email"):
            target = queries.find_user_by_email_ci(ser.validated_data["email"])  # helper istnieje u Ciebie
        if not target:
            return Response({"detail": "User not found"}, status=404)

        try:
            m = commands.add_member(
                actor=request.user, seller=seller,
                target_user=target, role=ser.validated_data["role"]
            )
            return Response(SellerMembershipResponse(m).data, status=201)
        except PermissionError as e:
            return Response({"detail": str(e)}, status=403)
        except TokenInvalid as e:
            return Response({"detail": str(e)}, status=400)

    def partial_update(self, request, seller_public_id: str = None, member_public_id: str = None):
        seller = self._get_seller(seller_public_id)
        if not queries.can_manage_members(request.user, seller):
            return Response({"detail": "Forbidden"}, status=403)
        ser = SellerMembershipUpdateRoleRequest(data=request.data)
        ser.is_valid(raise_exception=True)

        member = queries.get_membership_by_public_id_for_seller(member_public_id, seller)
        if member is None:
            return Response({"detail": "Not found"}, status=404)

        try:
            m = commands.update_member_role(
                actor=request.user, seller=seller, member=member, new_role=ser.validated_data["role"]
            )
            return Response(SellerMembershipResponse(m).data, status=200)
        except PermissionError as e:
            return Response({"detail": str(e)}, status=403)
        except TokenInvalid as e:
            return Response({"detail": str(e)}, status=400)

    def destroy(self, request, seller_public_id: str = None, member_public_id: str = None):
        seller = self._get_seller(seller_public_id)
        if not queries.can_manage_members(request.user, seller):
            return Response({"detail": "Forbidden"}, status=403)

        member = queries.get_membership_by_public_id_for_seller(member_public_id, seller)
        if member is None:
            return Response({"detail": "Not found"}, status=404)

        try:
            commands.remove_member(actor=request.user, seller=seller, member=member)
            return Response(status=204)
        except PermissionError as e:
            return Response({"detail": str(e)}, status=403)
        except TokenInvalid as e:
            return Response({"detail": str(e)}, status=400)

class MySellerMembershipsViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    /api/sellers/mine/memberships [GET]
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SellerMembershipResponse
    filterset_class = SellerMembershipFilter
    ordering_fields = ("created_at", "role")
    search_fields = ("seller_profile__slug", "seller_profile__company_name", "user__email")

    def get_queryset(self):
        return queries.memberships_for_user(self.request.user)


class SellerContextView(viewsets.ViewSet):
    """
    GET /api/sellers/context/
    Zwraca: {in_shop, role, seller_public_id, seller_slug, allowed_tabs}
    """
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        u = request.user
        cache_key = f"seller_ctx:{u.id}"
        if request.query_params.get("refresh") != "1":
            cached = cache.get(cache_key)
            if cached:
                return Response(SellerContextResponse(cached).data, status=200)

        # 1) jeśli user posiada własny SellerProfile – traktujemy to jako OWNER
        sp = (SellerProfile.objects
              .only("public_id", "slug", "owner_id")
              .filter(owner=u).first())
        if sp:
            data = {
                "in_shop": True,
                "role": "OWNER",
                "seller_public_id": sp.public_id,
                "seller_slug": sp.slug,
            }
        else:
            # 2) w przeciwnym razie – wybierz najlepsze aktywne membership
            mem = queries.best_membership_for_user(u)
            if mem:
                data = {
                    "in_shop": True,
                    "role": mem.role,
                    "seller_public_id": mem.seller_profile.public_id,
                    "seller_slug": mem.seller_profile.slug,
                }
            else:
                data = {"in_shop": False, "role": None,
                        "seller_public_id": None, "seller_slug": None}

        cache.set(cache_key, data, 60)  # TTL 60s
        return Response(SellerContextResponse(data).data, status=200)