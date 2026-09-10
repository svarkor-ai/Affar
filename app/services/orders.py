"""Orders service (contract C13 rev-2 / C14) — business rules for sales orders.

Owns order lifecycle transitions (draft -> confirmed). Price integrity is
server-side: ``unit_price`` on each OrderLine is a SNAPSHOT of the item's
current ``unit_price`` taken at creation, and ``subtotal`` is computed here as
qty * snapshot (never client-supplied) — invariant I?/C14.

Confirm applies a stock-out through ``catalog.adjust_stock`` (the single owner
of ``qty_on_hand``, invariant I2) in the same transaction, so a failure rolls
back the whole confirm and no partial decrement is left behind.
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Customer, Item, Order, OrderLine
from app.models.order import ORDER_STATUS

# Staff who place and manage internal sales orders. The customer role is served
# by a separate (later) self-service card and never touches this surface.
ORDER_ROLES = ["admin", "sales", "finance"]

# Allowed forward transitions on confirm. Anything but draft -> confirmed is not
# initiatable by this card (shipped/delivered land with tracking).
CONFIRMABLE = ("draft", "confirmed")


def get_order_or_404(db: Session, order_id: int) -> Order:
    """Return the order with *order_id* or raise 404."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


def create_order(db: Session, payload) -> Order:
    """Create a draft Order, snapshotting each line's price from the Item.

    *payload* carries only {customer_id, lines:[{item_id, qty}]}. The customer
    must exist and every referenced item must exist (404 otherwise). If an item
    is inactive it is still valid to order against its snapshot — availability
    is governed by stock on confirm, not the active flag here.
    """
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    # MC 1175.5: an AVAKTIVERAD customer cannot take new orders — the flag
    # gates NEW transactions only; historical rows stay untouched (410, the
    # resource exists but is deactivated; PUT cannot revive it — only the
    # /active PATCH flips the flag).
    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Customer is deactivated",
        )

    order = Order(customer_id=customer.id, status="draft")

    # Resolve items once — O(n) lookups, uniform 404 for any unknown id.
    item_ids = [line.item_id for line in payload.lines]
    item_map = {it.id: it for it in db.query(Item).filter(Item.id.in_(item_ids)).all()}
    for line in payload.lines:
        item = item_map.get(line.item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item {line.item_id} not found",
            )
        snapshot = item.unit_price
        subtotal = (Decimal(line.qty) * snapshot).quantize(Decimal("0.01"))
        order.lines.append(
            OrderLine(
                item_id=item.id,
                qty=line.qty,
                unit_price=snapshot,
                subtotal=subtotal,
            )
        )

    db.add(order)
    db.commit()
    db.refresh(order)
    # Staff-only human label (rev-2 / C20). Not a public lookup key.
    order.tracking_ref = f"ORD-{order.id}"
    db.commit()
    db.refresh(order)
    return order


def replace_draft_lines(db: Session, order_id: int, lines) -> Order:
    """MC 1175.1 — replace the whole line set of a DRAFT order.

    ``lines`` carries only {item_id, qty} (C13 rev-2). Every line is
    re-snapshotted from the Item's current price (C14), so editing after a
    price change is safe: the client can never supply a price. Only a draft
    is editable — any other status is a 409, cancelled is a 410. The whole
    replacement is one transaction: an unknown item id rolls the edit back.
    """
    order = get_order_or_404(db, order_id)
    _require_draft_editable(order, "edit")

    # Resolve items once — O(n) lookups, uniform 404 for any unknown id.
    item_ids = [line.item_id for line in lines]
    item_map = {it.id: it for it in db.query(Item).filter(Item.id.in_(item_ids)).all()}
    new_lines = []
    for line in lines:
        item = item_map.get(line.item_id)
        if item is None:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item {line.item_id} not found",
            )
        snapshot = item.unit_price
        subtotal = (Decimal(line.qty) * snapshot).quantize(Decimal("0.01"))
        new_lines.append(
            OrderLine(
                item_id=item.id,
                qty=line.qty,
                unit_price=snapshot,
                subtotal=subtotal,
            )
        )

    # delete-orphan cascade drops the old rows when the collection is cleared.
    order.lines.clear()
    order.lines.extend(new_lines)
    order.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order_id: int) -> Order:
    """MC 1175.1 — cancel a DRAFT order (terminal; no stock was ever out).

    Draft-only: a confirmed order already consumed stock and may already have
    an invoice, so cancelling it needs a restock flow that does not exist yet
    (409 says exactly that). A cancelled order is terminal (409 on retry).
    """
    order = get_order_or_404(db, order_id)
    if order.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order is already cancelled",
        )
    if order.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Order is {order.status!r}; only a draft can be cancelled "
                "(a confirmed order needs a restock, not a cancel)"
            ),
        )
    order.status = "cancelled"
    order.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
    return order


def _require_draft_editable(order: Order, verb: str) -> None:
    """Guard: *verb* is allowed on a draft only; other statuses explain why."""
    if order.status == "draft":
        return
    if order.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Order is cancelled; it cannot be {verb}ed",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Order is {order.status!r}; only a draft can be {verb}ed",
    )


def list_orders(db: Session) -> list[Order]:
    """Return all orders, newest first."""
    return (
        db.query(Order)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )


def confirm_order(db: Session, order_id: int) -> Order:
    """Transition the order draft -> confirmed, applying the stock-out (I2).

    Price snapshots are fixed at creation (C14) — confirming never re-prices.
    Confirm is atomic: it schedules the stock decrements and commits ONCE, so
    an insufficient-stock failure raises 409/400 and leaves both the order
    status and every item's stock unchanged (no partial decrement).
    """
    order = get_order_or_404(db, order_id)

    if order.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is already {order.status!r}; only a draft can be confirmed",
        )

    # Pre-validate every line against available stock before mutating.
    for ol in order.lines:
        item = db.get(Item, ol.item_id)
        # Item should always resolve (FK), but a deleted row is a 400, not 500.
        if item is None:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Item {ol.item_id} no longer exists; cannot confirm",
            )
        if item.qty_on_hand < ol.qty:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Insufficient stock for item {ol.item_id}: "
                    f"need {ol.qty}, have {item.qty_on_hand}"
                ),
            )

    # Apply the stock-out through the single owner of qty_on_hand (I2).
    for ol in order.lines:
        catalog_adjust(db, ol.item_id, -ol.qty)

    order.status = "confirmed"
    order.updated_at = datetime.now(UTC)

    # C21 rev-3: every confirmed order immediately gets its DeliveryTrack +
    # first 'placed' event, created in THIS transaction (atomic with confirm).
    from app.services.tracking import create_track_for_order

    create_track_for_order(db, order.id)

    db.commit()
    db.refresh(order)
    return order


def catalog_adjust(db: Session, item_id: int, delta: int) -> None:
    """Thin bridge to ``catalog.adjust_stock`` (keeps I2 the sole stock owner).

    Imported locally to avoid a circular import at module load (catalog does
    not import orders).
    """
    from app.services import catalog

    catalog.adjust_stock(db, item_id, delta)
