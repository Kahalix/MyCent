from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import (
    RegisterView, ConfirmRegistrationView, LoginView, RefreshView, LogoutView,
    ForgotPasswordView, ResetPasswordView, ChangeEmailRequestView, ConfirmEmailChangeView,
    PublicUserViewSet, SelfUserViewSet, AdminUserViewSet,
    PublicSellerProfileViewSet, MySellerProfileViewSet, AdminSellerProfileViewSet,
    MySellerBankAccountViewSet, AdminSellerBankAccountViewSet,
    SellerMembersViewSet, MySellerMembershipsViewSet, ChangePasswordView,
    SellerContextView, CsrfView, WsTokenView,
)

app_name = "identity"

router = DefaultRouter()

router.register(r"api/auth/register", RegisterView, basename="register")
router.register(r"api/auth/confirm-registration", ConfirmRegistrationView, basename="confirm-registration")
router.register(r"api/auth/login", LoginView, basename="login")
router.register(r"api/auth/refresh", RefreshView, basename="refresh")
router.register(r"api/auth/logout", LogoutView, basename="logout")
router.register(r"api/auth/forgot-password", ForgotPasswordView, basename="forgot-password")
router.register(r"api/auth/reset-password", ResetPasswordView, basename="reset-password")
router.register(r"api/auth/change-email", ChangeEmailRequestView, basename="change-email")
router.register(r"api/auth/change-password", ChangePasswordView, basename="change-password")
router.register(r"api/auth/confirm-email-change", ConfirmEmailChangeView, basename="confirm-email-change")
router.register(r"api/auth/csrf", CsrfView, basename="csrf")
router.register(r"api/auth/ws-token", WsTokenView, basename="ws-token")

router.register(r"api/public/users", PublicUserViewSet, basename="public-users")
router.register(r"api/admin/users", AdminUserViewSet, basename="admin-users")

router.register(r"api/public/sellers", PublicSellerProfileViewSet, basename="public-sellers")
router.register(r"api/admin/sellers", AdminSellerProfileViewSet, basename="admin-sellers")

router.register(r"api/sellers/mine/bank-accounts", MySellerBankAccountViewSet, basename="my-bank-accounts")
router.register(r"api/admin/seller-bank-accounts", AdminSellerBankAccountViewSet, basename="admin-bank-accounts")
router.register(r"api/sellers/mine/memberships", MySellerMembershipsViewSet, basename="my-memberships")

me_user = SelfUserViewSet.as_view({"get": "retrieve", "patch": "partial_update"})
me_avatar = SelfUserViewSet.as_view({"post": "upload_avatar", "delete": "delete_avatar"})

my_seller = MySellerProfileViewSet.as_view({"get": "retrieve", "post": "create", "patch": "partial_update"})
my_seller_logo = MySellerProfileViewSet.as_view({"post": "upload_logo", "delete": "delete_logo"})
my_seller_banner = MySellerProfileViewSet.as_view({"post": "upload_banner", "delete": "delete_banner"})

seller_members_list = SellerMembersViewSet.as_view({"get": "list", "post": "create"})
seller_member_detail = SellerMembersViewSet.as_view({"patch": "partial_update", "delete": "destroy"})
seller_members_candidates = SellerMembersViewSet.as_view({"get": "candidates"})

seller_context = SellerContextView.as_view({"get": "list"})

urlpatterns = [
    path("", include(router.urls)),

    path("api/users/me/", me_user, name="users-me"),
    path("api/users/me/avatar/", me_avatar, name="users-me-avatar"),

    path("api/sellers/mine/", my_seller, name="sellers-mine"),
    path("api/sellers/mine/logo/", my_seller_logo, name="sellers-mine-logo"),
    path("api/sellers/mine/banner/", my_seller_banner, name="sellers-mine-banner"),

    path("api/sellers/<str:seller_public_id>/members/candidates/", seller_members_candidates, name="seller-members-candidates"),
    path("api/sellers/<str:seller_public_id>/members/", seller_members_list, name="seller-members"),
    path("api/sellers/<str:seller_public_id>/members/<str:member_public_id>/", seller_member_detail, name="seller-member-detail"),
    path("api/sellers/context/", seller_context, name="seller-context"),
]
