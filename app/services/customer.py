"""Customer service (contract C9) — the CRUD layer behind /api/customers.

Small, thin, and consistent with the catalog/supplier service style: each
function takes a Session and an optional payload and returns an ORM Customer
(the router projects it onto CustomerOut). No money arithmetic here (C23: the
customer aggregate carries no monetary wire field).
"""

from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Customer

if TYPE_CHECKING:  # pragma: no cover
    from app.schemas.customer import CustomerIn


def get_customer_or_404(db: Session, customer_id: int) -> Customer:
    """Return the customer with *customer_id* or raise 404."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return customer


def list_customers(db: Session) -> list[Customer]:
    """Return all customers ordered by name (C9)."""
    return db.query(Customer).order_by(Customer.name).all()


def create_customer(db: Session, payload: "CustomerIn") -> Customer:
    """Persist and return a new Customer from a CustomerIn payload (C9)."""
    customer = Customer(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(db: Session, customer_id: int, payload: "CustomerIn") -> Customer:
    """Apply CustomerIn fields to the customer with *customer_id* (C9)."""
    customer = get_customer_or_404(db, customer_id)
    customer.name = payload.name
    customer.email = payload.email
    customer.phone = payload.phone
    customer.address = payload.address
    db.commit()
    db.refresh(customer)
    return customer
