"""Supplier service (contract C12) — the CRUD layer behind /api/suppliers.

Small, thin, and consistent with the catalog service style: each function
takes a Session and an optional payload and returns an ORM Supplier (the
router projects it onto SupplierOut). No money arithmetic here (C23: the
supplier aggregate carries no monetary wire field).
"""

from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Supplier

if TYPE_CHECKING:  # pragma: no cover
    from app.schemas.supplier import SupplierIn


def get_supplier_or_404(db: Session, supplier_id: int) -> Supplier:
    """Return the supplier with *supplier_id* or raise 404."""
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )
    return supplier


def list_suppliers(db: Session) -> list[Supplier]:
    """Return all suppliers ordered by name (C12)."""
    return db.query(Supplier).order_by(Supplier.name).all()


def create_supplier(db: Session, payload: "SupplierIn") -> Supplier:
    """Persist and return a new Supplier from a SupplierIn payload (C12)."""
    supplier = Supplier(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        payment_terms=payload.payment_terms,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(db: Session, supplier_id: int, payload: "SupplierIn") -> Supplier:
    """Apply SupplierIn fields to the supplier with *supplier_id* (C12)."""
    supplier = get_supplier_or_404(db, supplier_id)
    supplier.name = payload.name
    supplier.email = payload.email
    supplier.phone = payload.phone
    supplier.address = payload.address
    supplier.payment_terms = payload.payment_terms
    db.commit()
    db.refresh(supplier)
    return supplier
