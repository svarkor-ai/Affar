"""Sales-orders router (contract C13 rev-2 / C14; MC 1175.1 editability).

    POST  /api/orders                      OrderIn -> OrderOut   [admin, sales, finance]
    GET   /api/orders                      -> list[OrderOut]     [admin, sales, finance]
    GET   /api/orders/{order_id}           -> OrderOut           [admin, sales, finance]
    PATCH /api/orders/{order_id}           OrderPatch -> OrderOut     [admin, sales]
    PATCH /api/orders/{order_id}/status    OrderStatusPatch -> OrderOut [admin, sales]
    POST  /api/orders/{order_id}/confirm   -> OrderOut           [admin, sales, finance]

Price integrity lives in the service layer (server-side snapshot, C14); this
router only projects ORM rows onto the OrderOut wire schema — never returns raw
ORM objects and never accepts unit_price from the client. Stock is touched ONLY
by ``catalog.adjust_stock`` via the service (I2 single-owner rule) on confirm.
MC 1175.1: drafts are editable (replace lines, cancel) — both draft-only, both
price-blind (C14 holds through the edit path).
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.order import OrderIn, OrderOut, OrderPatch, OrderStatusPatch

from app.services import orders as orders_service

router = APIRouter(prefix="/api/orders", tags=["orders"])

# Edit surface is narrower than read: finance reads and confirms, never edits.
ORDER_EDIT_ROLES = ["admin", "sales"]


@router.post("", response_model=OrderOut)
def create_order(
    body: OrderIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(orders_service.ORDER_ROLES)),
) -> OrderOut:
    order = orders_service.create_order(db, body)
    return _order_to_out(order)


@router.get("", response_model=list[OrderOut])
def list_orders(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(orders_service.ORDER_ROLES)),
) -> list[OrderOut]:
    return [_order_to_out(o) for o in orders_service.list_orders(db)]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(orders_service.ORDER_ROLES)),
) -> OrderOut:
    order = orders_service.get_order_or_404(db, order_id)
    return _order_to_out(order)


@router.patch("/{order_id}", response_model=OrderOut)
def patch_order(
    order_id: int,
    body: OrderPatch,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ORDER_EDIT_ROLES)),
) -> OrderOut:
    """Replace the line set of a DRAFT order (MC 1175.1). Prices re-snapshot."""
    order = orders_service.replace_draft_lines(db, order_id, body.lines)
    return _order_to_out(order)


@router.patch("/{order_id}/status", response_model=OrderOut)
def patch_order_status(
    order_id: int,
    body: OrderStatusPatch,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ORDER_EDIT_ROLES)),
) -> OrderOut:
    """Status transition on an order — currently ``cancel`` only (MC 1175.1)."""
    if body.status != "cancel":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported status {body.status!r}; allowed: cancel",
        )
    order = orders_service.cancel_order(db, order_id)
    return _order_to_out(order)


@router.post("/{order_id}/confirm", response_model=OrderOut)
def confirm_order(
    order_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(orders_service.ORDER_ROLES)),
) -> OrderOut:
    order = orders_service.confirm_order(db, order_id)
    return _order_to_out(order)


def _order_to_out(order) -> OrderOut:
    """Project an ORM Order (with loaded lines) onto the OrderOut field set.

    ``total`` is the server-summed line subtotals; ``status`` is the closed
    ORDER_STATUS set; tracking_ref stays off the wire (staff-only, C20).
    """
    total = sum((ol.subtotal for ol in order.lines), Decimal("0.00")).quantize(
        Decimal("0.01")
    )
    return OrderOut(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        total=total,
        created_at=order.created_at.astimezone(UTC).isoformat(),
        lines=[
            {
                "id": ol.id,
                "item_id": ol.item_id,
                "qty": ol.qty,
                "unit_price": ol.unit_price,
                "subtotal": ol.subtotal,
            }
            for ol in order.lines
        ],
    )
