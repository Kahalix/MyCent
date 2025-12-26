from __future__ import annotations
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework import viewsets, mixins, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from django.http import HttpResponse

from pawns.services.printing import render_receipt_pdf as build_pawn_receipt_pdf
from pawns.services.printing import render_receipt_csv as build_pawn_receipt_csv
from pawns.services.printing import export_pawns_csv as export_pawns_list_csv

from pawns.services.commands import (
    attach_customer_to_pawn, detach_customer_from_pawn, ensure_customer_for_pawn,
)


from common.services.idempotency import get_existing, save_result
from pawns.models import Pawn
from pawns.serializers import PawnResponse, PawnCreateRequest, PawnExtendRequest
from pawns.services import commands, queries
from pawns.filters import PawnFilter
from identity.models import SellerProfile
from customers.models import Customer
from listings.models import ItemSet
from transactions.serializers import TransactionResponse

User = get_user_model()

def _ensure_membership(user, seller: SellerProfile) -> bool:
    return seller.memberships.filter(user=user, is_active=True).exists()

# ===== SELLER =====
class SellerPawnViewSet(mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PawnResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PawnFilter
    ordering_fields = ("created_at","due_date","start_date")

    def get_queryset(self):
        return queries.seller_pawns_qs(self.request.user)

    @action(detail=False, methods=["post"], url_path="create")
    def create_pawn(self, request):
        ser = PawnCreateRequest(data=request.data); ser.is_valid(raise_exception=True)
        seller = get_object_or_404(SellerProfile, public_id=ser.validated_data["seller_public_id"])
        if not _ensure_membership(request.user, seller):
            return Response({"detail": "Brak uprawnień (wymagana aktywna rola w sklepie)."}, status=403)

        cust = None
        if ser.validated_data.get("customer_public_id"):
            cust = get_object_or_404(Customer, public_id=ser.validated_data["customer_public_id"])

        # mapuj pozycje
        lines = []
        for row in ser.validated_data["lines"]:
            iset = None
            pid = row.get("item_set_public_id")
            if pid:
                iset = ItemSet.objects.filter(public_id=pid).first()
            lines.append({
                "title": row.get("title") or (iset.set_name if iset else "Pozycja"),
                "description": row.get("description", ""),
                "quantity": int(row.get("quantity", 1)),
                "appraisal_value": row.get("appraisal_value"),
                "item_set": iset,
                "item_snapshot": (row.get("item_snapshot") or {}) if not iset else {},
            })

        pawn = commands.create_pawn(
            operator=request.user, seller=seller,
            principal=ser.validated_data["principal"],
            due_in_days=int(ser.validated_data.get("due_in_days",30)),
            customer=cust,
            customer_snapshot_override=ser.validated_data.get("customer_snapshot"),
            lines=lines,
        )
        return Response(PawnResponse(pawn).data, status=201)

    @action(detail=True, methods=["post"], url_path="extend")
    def extend(self, request, public_id=None):
        pawn = self.get_object()
        ser = PawnExtendRequest(data=request.data); ser.is_valid(raise_exception=True)
        commands.extend_pawn(pawn=pawn, days=int(ser.validated_data["days"]), operator=request.user)
        pawn.refresh_from_db()
        return Response(PawnResponse(pawn).data, status=200)

    @action(detail=True, methods=["post"], url_path="redeem")
    def redeem(self, request, public_id=None):
        pawn = self.get_object()
        pawn = commands.redeem_pawn(pawn=pawn, operator=request.user)
        return Response(PawnResponse(pawn).data, status=200)

    @action(detail=True, methods=["post"], url_path="forfeit")
    def forfeit(self, request, public_id=None):
        pawn = self.get_object()
        pawn = commands.forfeit_pawn(pawn=pawn, operator=request.user, create_listing=True)
        return Response(PawnResponse(pawn).data, status=200)

    @action(detail=True, methods=["get"], url_path="receipt.pdf")
    def receipt_pdf(self, request, public_id=None):
        pawn = self.get_object()
        try:
            data = build_pawn_receipt_pdf(pawn)  # bytes
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=500)
        filename = f"pawn_{pawn.public_id}.pdf"
        resp = HttpResponse(data, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Content-Length"] = str(len(data))
        return resp

    @action(detail=True, methods=["get"], url_path="receipt.csv")
    def receipt_csv(self, request, public_id=None):
        pawn = self.get_object()
        data = build_pawn_receipt_csv(pawn)
        filename = f"pawn_{pawn.public_id}.csv"
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @action(detail=False, methods=["get"], url_path="export.csv")
    def export_csv(self, request):
        # eksport listy (z uwzględnieniem filtrów)
        qs = self.filter_queryset(self.get_queryset())
        data = export_pawns_list_csv(qs)
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="pawns_export.csv"'
        return resp

     # ==== AKCJE KLIENTA ====
    @action(detail=True, methods=["post"], url_path="attach-customer")
    def attach_customer(self, request, public_id=None):
        pawn = self.get_object()
        pid = (request.data or {}).get("customer_public_id", "")
        if not pid:
            return Response({"detail": "Brak customer_public_id."}, status=400)
        try:
            c = Customer.objects.get(public_id=pid)
        except Customer.DoesNotExist:
            return Response({"detail": "Nie znaleziono klienta."}, status=404)
        attach_customer_to_pawn(pawn=pawn, customer=c, update_snapshot=True)
        return Response(PawnResponse(pawn).data, status=200)

    @action(detail=True, methods=["post"], url_path="detach-customer")
    def detach_customer(self, request, public_id=None):
        pawn = self.get_object()
        detach_customer_from_pawn(pawn=pawn)
        return Response(PawnResponse(pawn).data, status=200)

    @action(detail=True, methods=["post"], url_path="ensure-customer")
    def ensure_customer(self, request, public_id=None):
        pawn = self.get_object()
        data = request.data or {}
        res = ensure_customer_for_pawn(
            pawn=pawn,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            address=data.get("address") or {},
            document_type=data.get("document_type", ""),
            document_number=data.get("document_number", ""),
            birth_date=data.get("birth_date"),
            allow_update_email=bool(data.get("allow_update_email", False)),
            allow_update_phone=bool(data.get("allow_update_phone", False)),
        )
        if res.get("result") == "conflict":
            return Response(
                {"detail": "Znaleziono wielu kandydatów - wybierz ręcznie.", "candidates": res["candidates"]},
                status=409
            )
        return Response({
            "result": res["result"],
            "customer_public_id": res.get("customer_public_id"),
            "pawn": PawnResponse(pawn).data
        }, status=200 if res["result"] == "attached" else 201)



# ===== USER (klient) =====
class UserPawnViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PawnResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PawnFilter
    ordering_fields = ("created_at","due_date","start_date")

    def get_queryset(self):
        return queries.user_pawns_qs(self.request.user)

    # @action(detail=True, methods=["post"], url_path="extend")
    # def extend(self, request, public_id=None):
    #     pawn = self.get_object()
    #     ser = PawnExtendRequest(data=request.data); ser.is_valid(raise_exception=True)
    #     commands.extend_pawn(pawn=pawn, days=int(ser.validated_data["days"]), operator=request.user)
    #     pawn.refresh_from_db()
    #     return Response(PawnResponse(pawn).data, status=200)

    @action(detail=True, methods=["post"], url_path="extend-intent")
    def extend_intent(self, request, public_id=None):
        pawn = self.get_object()
        ser = PawnExtendRequest(data=request.data);
        ser.is_valid(raise_exception=True)
        days = int(ser.validated_data["days"])

        idem_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
        fp = f"{pawn.public_id}:{days}"

        if idem_key:
            existing = get_existing(user=request.user, scope="pawns:extend", fingerprint=fp, key=idem_key)
            if existing:
                pid = (existing.target_ids or [None])[0]
                tx = Transaction.objects.filter(public_id=pid, user=request.user, type="PAWN_EXTENSION").first()
                if tx:
                    return Response(TransactionResponse(tx).data, status=200)

        tx = commands.create_extension_transaction(pawn=pawn, days=days, operator=request.user)

        if idem_key:
            save_result(user=request.user, scope="pawns:extend", fingerprint=fp,
                        key=idem_key, target_type="TX", target_ids=[tx.public_id])

        return Response(TransactionResponse(tx).data, status=201)


# ===== ADMIN =====
class AdminPawnViewSet(mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = PawnResponse
    lookup_field = "public_id"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PawnFilter
    ordering_fields = ("created_at","due_date","start_date")
    search_fields = ("customer_snapshot",)

    def get_queryset(self):
        return queries.admin_pawns_qs()

    @action(detail=False, methods=["get"], url_path="export.csv")
    def export_csv(self, request):
        qs = self.filter_queryset(self.get_queryset())
        data = export_pawns_list_csv(qs)
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="pawns_export.csv"'
        return resp
