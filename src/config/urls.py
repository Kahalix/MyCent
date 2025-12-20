from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [

    # SPA / HTML
    path("", include("core.urls")),


    path("admin/", admin.site.urls),



    # Chat (HTML + websockets)
    path("", include("chat.urls")),

    # API Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),

    # API – moduły
    path("", include("identity.urls")),
    path("", include("catalog.urls")),
    path("", include("coupons.urls")),
    path("", include("listings.urls")),
    path("", include("shipping.urls")),
    path("", include("services.urls")),
    path("", include("orders.urls")),
    path("", include("transactions.urls")),
    path("", include("pawns.urls")),
    path("", include("carts.urls")),
    path("", include("customers.urls")),
    path("", include("payments.urls")),
    path("", include("saved.urls")),
]

# Serwowanie plików statycznych/mediów tylko w DEV
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=getattr(settings, "STATIC_ROOT", None))

handler404 = "core.views.error_404"
handler500 = "core.views.error_500"
handler403 = "core.views.error_403"
handler400 = "core.views.error_400"
