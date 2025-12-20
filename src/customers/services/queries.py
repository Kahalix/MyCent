from __future__ import annotations
from identity.models import User
from customers.services import repositories as repo

def admin_customers_qs():
    return repo.admin_customers_qs()

def seller_customers_qs(user: User):
    return repo.seller_customers_qs(user)

def user_customers_qs(user: User):
    return repo.user_customers_qs(user)
