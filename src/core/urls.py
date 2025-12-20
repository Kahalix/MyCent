from django.urls import path
from . import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("login", views.login, name="login"),
    path("register", views.register, name="register"),
    path("forgot", views.forgot, name="forgot"),
    path("reset", views.reset_password, name="reset"),
    path("confirm-email", views.confirm_email, name="confirm_email"),
    path("profile", views.profile, name="profile"),
    path("shipping", views.shipping, name="shipping"),

    # SELLER
    path("seller", views.my_seller, name="my_seller"),
    path("seller/offers/new", views.offer_new, name="offer_new"),
    path("seller/offers/<str:public_id>", views.offer_edit, name="offer_edit"),
    path("seller/orders", views.seller_orders_view, name="seller_orders"),
    path("seller/orders/<str:order_public_id>", views.seller_order_view, name="seller_order_detail"),
    path("seller/orders/new/offline-sale",  views.seller_offline_form, name="seller_offline_form"),
    path("seller/orders/new/pawn-purchase", views.seller_pawn_form,    name="seller_pawn_form"),


    # USER
    path("me", views.my_offers, name="my_offers"),
    path("me/offers/new", views.my_offer_new, name="my_offer_new"),
    path("me/offers/<str:public_id>", views.my_offer_edit, name="my_offer_edit"),

    # MODERATOR
    path("moderation", views.moderation_user_offers, name="moderation_user_offers"),

    ## CART
    path("cart", views.cart_view, name="cart"),
    ## PAYMENTS
    path("pay", views.pay_view, name="pay"),
    path("pay/<str:tx_public_id>", views.pay_view, name="pay_detail"),
    path("transactions", views.transactions_view, name="transactions"),
    path("payments", views.payments_view, name="payments"),
    path("orders", views.buyer_orders_view, name="buyer_orders"),
    path("orders/<str:order_public_id>", views.buyer_order_detail_view, name="buyer_order_detail"),

    # SKLEP
    path("offers", views.offers_public, name="offers_public"),
    path("shop/<str:seller_slug>", views.shop, name="shop"),
    path("i/<slug:slug>", views.item_detail, name="item_detail"),
    path("u/<str:public_id>", views.user_public, name="user_public"),

    # PAWNS
    path("pawns", views.user_pawns_view, name="user_pawns"),
    path("pawns/<str:pawn_public_id>", views.user_pawn_detail_view, name="user_pawn_detail"),
    path("seller/pawns", views.seller_pawns_view, name="seller_pawns"),
    path("seller/pawns/new", views.seller_pawn_new, name="seller_pawn_new"),
    path("seller/pawns/<str:pawn_public_id>", views.seller_pawn_detail_view, name="seller_pawn_detail"),

    # COUPONS
    path("coupons", views.coupons_my, name="coupons_my"),
    path("coupons/shop", views.coupons_shop, name="coupons_shop"),

    # CHAT
    path("chat", views.chat_inbox, name="chat_inbox"),
    path("chat/t/<str:thread_public_id>", views.chat_thread, name="chat_thread"),

    # SAVED
    path("saved", views.saved_center, name="saved_center"),
    path("saved/searches/<str:public_id>", views.saved_search_results, name="saved_search_results"),
]
