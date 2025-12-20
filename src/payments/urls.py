from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import UserPaymentViewSet, SellerPaymentViewSet, AdminPaymentViewSet, PaymentWebhookView

app_name = "payments"

router = DefaultRouter()
router.register(r"api/users/me/payments",     UserPaymentViewSet,   basename="user-payments")
router.register(r"api/sellers/mine/payments", SellerPaymentViewSet, basename="seller-payments")
router.register(r"api/admin/payments",        AdminPaymentViewSet,  basename="admin-payments")

urlpatterns = [
    path("", include(router.urls)),
    path("api/payments/webhooks/<str:provider>/", PaymentWebhookView.as_view(), name="payments-webhook"),
]
