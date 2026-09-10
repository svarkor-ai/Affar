"""Purchase edit service (MC 1175.4) — redigering + makulering på inköpssidan.

Split from services.purchase (C19) so that module keeps its one concern
(create/list/status-advance). Three rules live here, mirroring the sales-side
edit services T1 (orders) / T2 (invoices) established:

* ``replace_po_lines`` — a DRAFT PO's line set can be replaced. unit_cost is
  legitimately wire-supplied on the purchase side (C18, negotiated per
  supplier) but bounded by the schema (Decimal ge=0, 12,2); line_total is
  recomputed SERVER-SIDE. Only draft is editable — ``ordered`` is a 409
  (the PO has left the house), ``cancelled`` is a 410 (terminal).

* ``set_ordered`` — the makulering-aware draft -> ordered transition. Not
  routed through set_po_status: that path would let a cancelled PO be
  re-ordered. Cancelled is 410 (terminal, never re-enterable); anything but
  draft is 409. Stock is untouched (I2) — only ``received`` ever moves stock.

* ``cancel_po`` — makulering. Cancelled is TERMINAL and OUTSIDE the forward
  lifecycle draft -> ordered -> received. A received PO already moved stock
  through the single-owner stock-in path, so cancelling it is a 409 (a
  reversal flow does not exist yet — same rule T1 applied to confirmed
  sales orders). Idempotency: re-cancel is a 409.
"""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Item, PurchaseOrder, PurchaseOrderLine
from app.services.purchase import get_po_or_404


def _require_draft_editable(po: PurchaseOrder, verb: str) -> None:
    """Guard: *verb* is allowed on a draft PO only (mirrors T1/T2)."""
    if po.status == "draft":
        return
    if po.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Purchase order {po.id} is cancelled; it cannot be {verb}ed",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Purchase order {po.id} is {po.status!r}; only a draft can be {verb}ed",
    )


def replace_po_lines(db: Session, po_id: int, lines) -> PurchaseOrder:
    """MC 1175.4 — replace the whole line set of a DRAFT purchase order.

    ``lines`` carry {item_id, qty, unit_cost} (C18 — cost IS wire-supplied
    here, unlike the sales side). line_total = qty * unit_cost is recomputed
    SERVER-SIDE from the schema-validated values. An unknown item id rolls
    the whole replacement back (404), same atomic rule as T1/T2.
    """
    po = get_po_or_404(db, po_id)
    _require_draft_editable(po, "edit")

    # Resolve items once — O(n) lookups, uniform 404, atomic rollback.
    item_ids = [ln.item_id for ln in lines]
    item_map = {it.id: it for it in db.query(Item).filter(Item.id.in_(item_ids)).all()}
    new_lines = []
    for ln in lines:
        if ln.item_id not in item_map:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item {ln.item_id} not found",
            )
        # Server-side money, Decimal-only (I7), from schema-validated values.
        line_total = (Decimal(ln.qty) * ln.unit_cost).quantize(Decimal("0.01"))
        new_lines.append(
            PurchaseOrderLine(
                po_id=po.id,
                item_id=ln.item_id,
                qty=ln.qty,
                unit_cost=ln.unit_cost,
                line_total=line_total,
            )
        )

    # delete-orphan cascade drops the old rows when the collection is cleared.
    po.lines.clear()
    po.lines.extend(new_lines)
    db.commit()
    db.refresh(po)
    return po


def set_ordered(db: Session, po_id: int) -> PurchaseOrder:
    """MC 1175.4 — makulering-aware draft -> ordered transition.

    Not routed through set_po_status: that path would let a cancelled PO be
    re-ordered. Cancelled is a 410 (terminal, never re-enterable); anything
    but draft is a 409. No stock moves here (I2 single owner).
    """
    po = get_po_or_404(db, po_id)
    if po.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Purchase order {po_id} is cancelled; it can never be ordered",
        )
    if po.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Purchase order {po_id} is {po.status!r}; "
                "only a draft can move to 'ordered'"
            ),
        )
    po.status = "ordered"
    db.commit()
    db.refresh(po)
    return po


def cancel_po(db: Session, po_id: int) -> PurchaseOrder:
    """MC 1175.4 — makulera a purchase order (terminal, never stock-affecting).

    Draft or ordered may be cancelled; received may NOT — stock already moved
    in via the single-owner path, so a received PO needs a reversal flow that
    does not exist yet (409 says exactly that, like T1's confirmed sales
    orders). Cancelled is terminal: re-cancel is 409, every other route into
    or out of it is 410 (set_po_status/set_ordered) or 409 (this module).
    """
    po = get_po_or_404(db, po_id)
    if po.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Purchase order {po_id} is already cancelled",
        )
    if po.status == "received":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Purchase order {po_id} is received; stock is already in — "
                "a received PO cannot be cancelled (needs a reversal, not a cancel)"
            ),
        )
    po.status = "cancelled"
    db.commit()
    db.refresh(po)
    return po
