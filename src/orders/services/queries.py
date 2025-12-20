from __future__ import annotations
from orders.services import repositories as repo
from identity.models import User, SellerProfile

def list_buyer_orders(user: User):
    return repo.buyer_orders_qs(user)

def list_seller_orders(seller: SellerProfile):
    return repo.seller_orders_qs(seller)

def list_admin_orders():
    return repo.admin_orders_qs()