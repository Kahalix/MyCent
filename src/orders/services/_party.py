# src/orders/services/_party.py
def make_customer_snapshot(*, first_name="", last_name="", email="", phone="",
                           address=None, doc_type="", doc_number="", birth_date=None):
    address = address or {}
    return {
        "first_name": first_name, "last_name": last_name,
        "email": email, "phone": phone,
        "address": {
            "line1": address.get("line1",""),
            "line2": address.get("line2",""),
            "postal_code": address.get("postal_code",""),
            "city": address.get("city",""),
            "country": address.get("country",""),
        },
        "document": {
            "type": doc_type, "number": doc_number,
        },
        "birth_date": str(birth_date) if birth_date else None,
    }

def snapshot_from_customer(customer) -> dict:
    return make_customer_snapshot(
        first_name=customer.first_name, last_name=customer.last_name,
        email=customer.email, phone=customer.phone,
        address={
            "line1": customer.address_line1,
            "line2": customer.address_line2,
            "postal_code": customer.postal_code,
            "city": customer.city, "country": customer.country,
        },
        doc_type=customer.document_type, doc_number=customer.document_number,
        birth_date=customer.birth_date,
    )

def snapshot_from_user(user) -> dict:
    # Minimal: user.email + phone (masz phone na User), imię/nazwisko jeśli trzymasz
    return make_customer_snapshot(
        first_name=getattr(user, "first_name", "") or "",
        last_name=getattr(user, "last_name", "") or "",
        email=user.email, phone=getattr(user, "phone_number", "") or "",
    )
