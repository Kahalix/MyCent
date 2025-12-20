from __future__ import annotations
from customers.models import Customer
from customers.services import repositories as repo
from customers.services.exceptions import NotFound

def create_customer(**payload) -> Customer:
    return repo.create_customer(**payload)

def update_customer(*, public_id: str, **payload) -> Customer:
    obj = repo.get_by_public_id(public_id)
    if not obj:
        raise NotFound("Customer not found.")
    return repo.update_customer(obj, **payload)

def delete_customer(*, public_id: str) -> None:
    obj = repo.get_by_public_id(public_id)
    if not obj:
        return
    repo.delete_customer(obj)
