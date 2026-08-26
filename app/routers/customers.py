"""Customers router (contract C9) — HTTP surface for customer master data.

    POST /api/customers  CustomerIn -> CustomerOut        [admin, sales]
    GET  /api/customers  -> list[CustomerOut]
    GET  /api/customers/{id} -> CustomerOut
    PUT  /api/customers/{id} CustomerIn -> CustomerOut

All customer-endpoint write+list routes are role-gated to the C9 staff set —
the customer role uses the tracking surface, it does not manage the master
customer records. Returns schema objects (C23), never raw ORM.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.customer import CustomerIn, CustomerOut

from app.services import customer as customer_service

# C9 allowed roles. Customer role deliberately absent.
CUSTOMER_ROLES = ["admin", "sales"]

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.post("", response_model=CustomerOut)
def create_customer(
    body: CustomerIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(CUSTOMER_ROLES)),
) -> CustomerOut:
    item = customer_service.create_customer(db, body)
    return CustomerOut(**customer_to_dict(item))


@router.get("", response_model=list[CustomerOut])
def list_customers(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(CUSTOMER_ROLES)),
) -> list[CustomerOut]:
    return [CustomerOut(**customer_to_dict(c)) for c in customer_service.list_customers(db)]


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(CUSTOMER_ROLES)),
) -> CustomerOut:
    c = customer_service.get_customer_or_404(db, customer_id)
    return CustomerOut(**customer_to_dict(c))


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    body: CustomerIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(CUSTOMER_ROLES)),
) -> CustomerOut:
    c = customer_service.update_customer(db, customer_id, body)
    return CustomerOut(**customer_to_dict(c))


def customer_to_dict(c) -> dict:
    """Project an ORM Customer onto the CustomerOut field set (C23 — no bare ORM)."""
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "created_at": c.created_at,
    }
