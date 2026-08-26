"""Purchase service (contract C19) — PO lifecycle + stock-in on receipt.

Single mechanism for the buy-side wire (C18/C19): every line's ``unit_cost``
is validated non-negative Decimal (12,2) by the schema, ``qty > 0`` by the
schema, and ``line_total = qty * unit_cost`` is recomputed SERVER-SIDE from
those validated values — so a PO total can never go negative (refutation 1
purchase-side fix). All money arithmetic runs on Decimal, never float (I7).

``status`` transitions live here too: on ``received`` each line triggers
stock-in via ``catalog.adjust_stock(db, item_id, +qty)`` — the single owner
of ``qty_on_hand`` (I2). No other code path writes stock.
"""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Item, PurchaseOrder, PurchaseOrderLine, Supplier
from app.services.catalog import adjust_stock

# Closed status set (C18) — the only values PATCH may set.
PO_STATUS: tuple[str, ...] = ("draft", "ordered", "received")


def get_po_or_404(db: Session, po_id: int) -> PurchaseOrder:
    """Return the PO with *po_id* or raise 404 (C19)."""
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found",
        )
    return po


def _get_supplier_or_404(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )
    return supplier


def _get_item_or_404(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return item


def create_po(db: Session, payload) -> PurchaseOrder:
    """Persist a PurchaseOrder with server-computed line totals (C19)."""
    # Validate FK targets up front so a bad supplier/item is a clean 404,
    # never a SQLAlchemy FK violation.
    _get_supplier_or_404(db, payload.supplier_id)
    po = PurchaseOrder(supplier_id=payload.supplier_id, status="draft")
    db.add(po)
    db.flush()

    for line in payload.lines:
        _get_item_or_404(db, line.item_id)
        # line_total computed server-side from the validated qty/unit_cost.
        line_total = Decimal(line.qty) * line.unit_cost
        db.add(
            PurchaseOrderLine(
                po_id=po.id,
                item_id=line.item_id,
                qty=line.qty,
                unit_cost=line.unit_cost,
                line_total=line_total,
            )
        )
    db.commit()
    db.refresh(po)
    return po


def list_pos(db: Session) -> list[PurchaseOrder]:
    """Return all purchase orders (C19)."""
    return db.query(PurchaseOrder).order_by(PurchaseOrder.id).all()


def set_po_status(db: Session, po_id: int, new_status: str) -> PurchaseOrder:
    """Transition a PO to *new_status*; on ``received`` stock-in each line.

    The status set is closed (C18): any value outside ``PO_STATUS`` is a 422.
    ``received`` is the only stock-affecting transition — it applies
    ``catalog.adjust_stock(db, item_id, +qty)`` per line (I2 single owner).
    """
    if new_status not in PO_STATUS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid purchase order status {new_status!r}; "
                f"allowed: {', '.join(PO_STATUS)}"
            ),
        )

    po = get_po_or_404(db, po_id)
    if new_status == "received" and po.status != "received":
        for line in po.lines:
            _get_item_or_404(db, line.item_id)
            adjust_stock(db, line.item_id, line.qty)  # stock-in
    po.status = new_status
    db.commit()
    db.refresh(po)
    return po
