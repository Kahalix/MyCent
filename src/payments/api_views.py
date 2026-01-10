from __future__ import annotations
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, mixins, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from django.conf import settings

from payments.payments_integrations.dummy import DummyClient
from payments.payments_integrations.stripe_client import StripeClient
from transactions.models import Transaction
from payments.models import Payment
from payments.serializers import (
    PaymentResponse, CreatePaymentRequest, ConfirmPaymentRequest, CancelPaymentRequest, PaymentSellerResponse
)
from payments.filters import PaymentFilter
from payments.services.commands import (
    create_payment_for_transaction, confirm_payment, cancel_active_payment, _award_points_after_success,
    mark_payment_failed_or_cancelled, mark_payment_succeeded, mark_payment_requires_action, mark_payment_processing
)

# idempotencja
from common.services.idempotency import get_existing, save_result

# ===== USER =====
class UserPaymentViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentResponse
    lookup_field = "public_id"

    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PaymentFilter
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return (Payment.objects
                .select_related("transaction")
                .filter(transaction__user=self.request.user)
                .order_by("-created_at"))

    @action(detail=False, methods=["post"], url_path="intents")
    def create_intent(self, request):
        ser = CreatePaymentRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        tx = get_object_or_404(Transaction, public_id=ser.validated_data["transaction_public_id"], user=request.user)
        idem_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
        if idem_key:
            existing = get_existing(user=request.user, scope="payments:intent", fingerprint=tx.public_id, key=idem_key)
            if existing:
                pid = (existing.target_ids or [None])[0]
                p = Payment.objects.filter(public_id=pid, transaction=tx).first()
                if p:
                    return Response(PaymentResponse(p).data, status=200)
        req_provider = (ser.validated_data.get("provider") or "").upper()
        p = create_payment_for_transaction(
            tx=tx,
            provider=req_provider or None,
            coupon_code=ser.validated_data.get("coupon_code") or None,
            user_coupon_public_id=ser.validated_data.get("user_coupon_public_id") or None,
        )
        if idem_key:
            save_result(user=request.user, scope="payments:intent", fingerprint=tx.public_id, key=idem_key,
                        target_type="PAYMENT", target_ids=[p.public_id])
        return Response(PaymentResponse(p).data, status=201)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, public_id=None):
        pay = self.get_object()
        ser = ConfirmPaymentRequest(data=request.data); ser.is_valid(raise_exception=True)
        succeed = (ser.validated_data["result"] == "success") if pay.provider == "SIM" else None
        pay = confirm_payment(payment=pay, succeed=succeed)
        return Response(PaymentResponse(pay).data, status=200)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, public_id=None):
        pay = self.get_object()
        ser = CancelPaymentRequest(data=request.data); ser.is_valid(raise_exception=True)
        pay = cancel_active_payment(payment=pay, reason=ser.validated_data.get("reason", ""))
        return Response(PaymentResponse(pay).data, status=200)


# ===== SELLER =====
class SellerPaymentViewSet(mixins.ListModelMixin,
                           mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentSellerResponse
    lookup_field = "public_id"

    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PaymentFilter
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return (Payment.objects
                .select_related("transaction")
                .filter(transaction__orders__seller_profile__memberships__user=self.request.user,
                        transaction__orders__seller_profile__memberships__is_active=True)
                .order_by("-created_at").distinct())


# ===== ADMIN =====
class AdminPaymentViewSet(mixins.ListModelMixin,
                          mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = PaymentResponse
    lookup_field = "public_id"

    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PaymentFilter
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return Payment.objects.select_related("transaction").all().order_by("-created_at")


# ===== WEBHOOK (SIM/STRIPE) =====
@method_decorator(csrf_exempt, name="dispatch")
class PaymentWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, provider: str):
        if provider.lower() == "stripe":
            try:
                client = StripeClient()
                evt = client.parse_webhook(request)
            except Exception as e:
                return Response({"detail": f"stripe webhook error: {e}"}, status=400)

            pid = evt.get("provider_payment_id")
            status = evt.get("status")
            if not pid:
                return Response({"detail": "payment_intent id missing"}, status=400)

            pay = (
                Payment.objects
                .filter(provider="STRIPE", provider_payment_id=pid)
                .select_related("transaction")
                .first()
            )
            if not pay:
                return Response({"detail": "payment not found"}, status=404)

            if status == "succeeded":
                mark_payment_succeeded(payment=pay, reason="Stripe webhook: succeeded")
            elif status in ("failed", "cancelled"):
                mark_payment_failed_or_cancelled(
                    payment=pay,
                    status="FAILED" if status == "failed" else "CANCELLED",
                    reason=f"Stripe webhook: {status}",
                )
            elif status == "requires_action":
                mark_payment_requires_action(payment=pay, reason="Stripe webhook: requires_action")
            elif status == "processing":
                mark_payment_processing(payment=pay, reason="Stripe webhook: processing")

            return Response({"ok": True}, status=200)

        # --- SIM ---

        client = DummyClient()
        evt = client.parse_webhook(request)
        pid = evt.get("provider_payment_id")
        status = evt.get("status")
        if not pid:
            return Response({"detail": "missing provider_payment_id"}, status=400)
        pay = (Payment.objects.filter(provider=client.provider_code, provider_payment_id=pid).select_related("transaction").first())
        if not pay:
            return Response({"detail": "payment not found"}, status=404)
        if status == "succeeded":
            mark_payment_succeeded(payment=pay, reason="Webhook: succeeded")
        elif status in ("failed","cancelled"):
            mark_payment_failed_or_cancelled(payment=pay, status="FAILED" if status == "failed" else "CANCELLED", reason=f"Webhook: {status}")
        return Response({"ok": True}, status=200)
