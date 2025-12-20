from django.shortcuts import render


# def _partial_or_page(request, partial, context=None):
#     """
#     Renderuje albo partiala (jeżeli HTMX request), albo pełną stronę z partialem.
#     context - dodatkowe dane przekazywane do szablonu.
#     """
#     if context is None:
#         context = {}
#
#     if request.headers.get("HX-Request"):
#         return render(request, partial, context)
#
#     return render(request, "app/page.html", {"partial": partial, **context})

def _partial_or_page(request, partial, context=None, status=200):
    """
    Renderuje albo partiala (jeżeli HTMX request), albo pełną stronę z partialem.
    context - dodatkowe dane przekazywane do szablonu.
    """
    context = context or {}
    if request.headers.get("HX-Request"):
        return render(request, partial, context=context, status=200)
    return render(request, "app/page.html", {"partial": partial, **context}, status=status)

def error_400(request, exception):
    return _partial_or_page(request, "app/partials/error_400.html", {"code": 400}, status=400)

def error_403(request, exception):
    return _partial_or_page(request, "app/partials/error_403.html", {"code": 403}, status=403)

def error_404(request, exception):
    return _partial_or_page(request, "app/partials/error_404.html", {"code": 404}, status=404)

def error_500(request):
    return _partial_or_page(request, "app/partials/error_500.html", {"code": 500}, status=500)

def csrf_failure_view(request, reason=""):
    return _partial_or_page(request, "app/partials/error_403.html", {"code": 403, "reason": reason}, status=403)

def home(request):
    return _partial_or_page(request, "app/partials/landing.html")


def login(request):
    return _partial_or_page(request, "app/partials/login.html")


def register(request):
    return _partial_or_page(request, "app/partials/register.html")


def forgot(request):
    return _partial_or_page(request, "app/partials/forgot.html")


def reset_password(request):
    return _partial_or_page(request, "app/partials/reset_password.html")


def confirm_email(request):
    return _partial_or_page(request, "app/partials/confirm_email.html")


def profile(request):
    return _partial_or_page(request, "app/partials/profile.html")


def shipping(request):
    return _partial_or_page(request, "app/partials/shipping.html")


def my_seller(request):
    return _partial_or_page(request, "app/partials/my_seller.html")


def offer_new(request):
    return _partial_or_page(request, "app/partials/seller_offer_form.html", {"editing_id": ""})


def offer_edit(request, public_id):
    return _partial_or_page(request, "app/partials/seller_offer_form.html", {"editing_id": public_id})

def my_offers(request):
    return _partial_or_page(request, "app/partials/user_offers_list.html")


def my_offer_new(request):
    return _partial_or_page(request, "app/partials/user_offer_form.html", {"editing_id": ""})


def my_offer_edit(request, public_id: str):
    return _partial_or_page(request, "app/partials/user_offer_form.html", {"editing_id": public_id})

def offers_public(request):
    # lista ogólnodostępna
    return _partial_or_page(request, "app/partials/public_offers.html")

def shop(request, seller_slug):
    # sklep konkretnego sprzedawcy
    return _partial_or_page(request, "app/partials/seller_shop.html", {"seller_slug": seller_slug})

def item_detail(request, slug):
    return _partial_or_page(request, "app/partials/item_detail.html", {"slug": slug})

def user_public(request, public_id):
    return _partial_or_page(request, "app/partials/user_public.html", {"user_public_id": public_id})

def cart_view(request):
    return _partial_or_page(request, "app/partials/cart.html", {})

def pay_view(request, tx_public_id: str = ""):
    ctx = {"tx_public_id": tx_public_id or ""}
    return _partial_or_page(request, "app/partials/pay.html", ctx)

def transactions_view(request):
    return _partial_or_page(request, "app/partials/transactions_list.html", {})

def payments_view(request):
    return _partial_or_page(request, "app/partials/payments_list.html", {})

def seller_order_view(request, order_public_id: str):
    return _partial_or_page(request, "app/partials/seller_order_detail.html", {"order_public_id": order_public_id})

def buyer_orders_view(request):
    return _partial_or_page(request, "app/partials/buyer_orders_list.html", {})

def buyer_order_detail_view(request, order_public_id: str):
    return _partial_or_page(request, "app/partials/buyer_order_detail.html", {"order_public_id": order_public_id})

def seller_orders_view(request):
    return _partial_or_page(request, "app/partials/seller_orders_list.html", {})

def seller_offline_form(request):
    return _partial_or_page(request, "app/partials/seller_order_offline_form.html", {})

def seller_pawn_form(request):
    return _partial_or_page(request, "app/partials/seller_order_pawn_form.html", {})

def user_pawns_view(request):
    return _partial_or_page(request, "app/partials/user_pawns_list.html", {})

def user_pawn_detail_view(request, pawn_public_id: str):
    return _partial_or_page(request, "app/partials/user_pawn_detail.html", {"pawn_public_id": pawn_public_id})

def seller_pawns_view(request):
    return _partial_or_page(request, "app/partials/seller_pawns_list.html", {})

def seller_pawn_new(request):
    return _partial_or_page(request, "app/partials/seller_pawn_form.html", {})

def seller_pawn_detail_view(request, pawn_public_id: str):
    return _partial_or_page(request, "app/partials/seller_pawn_detail.html", {"pawn_public_id": pawn_public_id})

def coupons_my(request):
    return _partial_or_page(request, "app/partials/coupons_my.html")

def coupons_shop(request):
    return _partial_or_page(request, "app/partials/coupons_shop.html")

def chat_inbox(request):
    return _partial_or_page(request, "app/partials/chat_inbox.html")

def chat_thread(request, thread_public_id: str):
    return _partial_or_page(request, "app/partials/chat_thread.html", {"thread_public_id": thread_public_id})

def saved_center(request):
    return _partial_or_page(request, "app/partials/saved_center.html")

def saved_search_results(request, public_id: str):
    return _partial_or_page(request, "app/partials/saved_search_results.html", {"saved_public_id": public_id})

def moderation_user_offers(request):
    return _partial_or_page(request, "app/partials/moderation_user_offers.html")