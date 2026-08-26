"""Purchase router (contract C19) — HTTP surface for purchase orders.

    POST  /api/purchase-orders  PurchaseOrderIn -> POut   [admin, procurement]
    GET   /api/purchase-orders  -> list[POut]
    GET   /api/purchase-orders/{id} -> POut
    PATCH /api/purchase-orders/{id}/status {status} -> POut

``received`` PATCH performs stock-in via the purchase service (which calls the
catalog `adjust_stock` — the single stock owner, I2). All surfaces return
schema objects (C23), never raw ORM. Roles are [admin, procurement].
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.purchase import (
    PurchaseOrderIn,
    PurchaseOrderLineOut,
    PurchaseOrderOut,
    PurchaseOrderStatusIn,
)

from app.services import purchase as purchase_service

# C19 allowed roles. Customer deliberately absent.
PURCHASE_ROLES = ["admin", "procurement"]

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])


@router.post("", response_model=PurchaseOrderOut)
def create_po(
    body: PurchaseOrderIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(PURCHASE_ROLES)),
) -> PurchaseOrderOut:
    po = purchase_service.create_po(db, body)
    return PurchaseOrderOut(**po_to_dict(po))


@router.get("", response_model=list[PurchaseOrderOut])
def list_pos(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(PURCHASE_ROLES)),
) -> list[PurchaseOrderOut]:
    return [PurchaseOrderOut(**po_to_dict(po)) for po in purchase_service.list_pos(db)]


@router.get("/{po_id}", response_model=PurchaseOrderOut)
def get_po(
    po_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(PURCHASE_ROLES)),
) -> PurchaseOrderOut:
    po = purchase_service.get_po_or_404(db, po_id)
    return PurchaseOrderOut(**po_to_dict(po))


@router.patch("/{po_id}/status", response_model=PurchaseOrderOut)
def set_po_status(
    po_id: int,
    body: PurchaseOrderStatusIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(PURCHASE_ROLES)),
) -> PurchaseOrderOut:
    po = purchase_service.set_po_status(db, po_id, body.status)
    return PurchaseOrderOut(**po_to_dict(po))


def _line_to_dict(line) -> dict:
    return {
        "id": line.id,
        "item_id": line.item_id,
        "qty": line.qty,
        "unit_cost": line.unit_cost,
        "line_total": line.line_total,
    }


def po_to_dict(po) -> dict:
    """Project an ORM PurchaseOrder onto the POut field set (C23 — no bare ORM)."""
    return {
        "id": po.id,
        "supplier_id": po.supplier_id,
        "status": po.status,
        "lines": [_line_to_dict(line) for line in po.lines],
    }
