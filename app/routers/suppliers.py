"""Suppliers router (contract C12) — HTTP surface for suppliers.

    POST /api/suppliers  SupplierIn -> SupplierOut        [admin, procurement]
    GET  /api/suppliers  -> list[SupplierOut]
    GET  /api/suppliers/{id} -> SupplierOut
    PUT  /api/suppliers/{id} SupplierIn -> SupplierOut

All supplier endpoints are role-gated to the C12 set — the customer role
never touches suppliers. Returns schema objects (C23), never raw ORM.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.supplier import SupplierIn, SupplierOut

from app.services import supplier as supplier_service

# C12 allowed roles. Customer deliberately absent.
SUPPLIER_ROLES = ["admin", "procurement"]

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.post("", response_model=SupplierOut)
def create_supplier(
    body: SupplierIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(SUPPLIER_ROLES)),
) -> SupplierOut:
    item = supplier_service.create_supplier(db, body)
    return SupplierOut(**supplier_to_dict(item))


@router.get("", response_model=list[SupplierOut])
def list_suppliers(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(SUPPLIER_ROLES)),
) -> list[SupplierOut]:
    return [SupplierOut(**supplier_to_dict(s)) for s in supplier_service.list_suppliers(db)]


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(SUPPLIER_ROLES)),
) -> SupplierOut:
    s = supplier_service.get_supplier_or_404(db, supplier_id)
    return SupplierOut(**supplier_to_dict(s))


@router.put("/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    body: SupplierIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(SUPPLIER_ROLES)),
) -> SupplierOut:
    s = supplier_service.update_supplier(db, supplier_id, body)
    return SupplierOut(**supplier_to_dict(s))


def supplier_to_dict(s) -> dict:
    """Project an ORM Supplier onto the SupplierOut field set (C23 — no bare ORM)."""
    return {
        "id": s.id,
        "name": s.name,
        "email": s.email,
        "phone": s.phone,
        "address": s.address,
        "payment_terms": s.payment_terms,
    }
