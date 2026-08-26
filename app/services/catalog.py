"""Catalog service (contract C8) — item CRUD + the single owner of qty_on_hand.

``adjust_stock`` is THE only place ``item.qty_on_hand`` is mutated (invariant
I2). Sales-order confirmation (stock-out) and purchase receipt (stock-in) both
call it; no other code path may write ``qty_on_hand`` directly. It is internal
(no router exposes it) — the wire never carries the item's price or stock delta
into the ledger here.
"""

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Item


def get_item_or_404(db: Session, item_id: int) -> Item:
    """Return the item with *item_id* or raise 404."""
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return item


def list_items(db: Session, active_only: bool | None = None) -> list[Item]:
    """Return items, optionally filtered to ``active`` ones (GET ?active=1)."""
    query = db.query(Item)
    if active_only is not None:
        query = query.filter(Item.active.is_(active_only))
    return query.order_by(Item.sku).all()


def create_item(db: Session, payload) -> Item:
    """Persist and return a new Item from an ItemIn payload (C8)."""
    item = Item(
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        unit_price=payload.unit_price,
        qty_on_hand=payload.qty_on_hand,
        active=True,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # sku is UNIQUE (C7) — surface a duplicate as a clean 409, not a 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An item with this sku already exists",
        ) from exc
    db.refresh(item)
    return item


def update_item(db: Session, item_id: int, payload) -> Item:
    """Apply ItemIn fields to the item with *item_id* and return it (C8)."""
    item = get_item_or_404(db, item_id)
    item.sku = payload.sku
    item.name = payload.name
    item.description = payload.description
    item.unit_price = payload.unit_price
    item.qty_on_hand = payload.qty_on_hand
    db.commit()
    db.refresh(item)
    return item


def adjust_stock(db: Session, item_id: int, delta: int) -> None:
    """Adjust an item's ``qty_on_hand`` by *delta* (I2 single-owner mutation).

    *delta* is negative on order confirmation (stock-out) and positive on
    purchase receipt (stock-in). Only ``catalog`` may call this — the catalog
    service is the acknowledged owner of the stock ledger. Raises ValueError
    for an unknown item so callers can 404 at their boundary.
    """
    item = db.get(Item, item_id)
    if item is None:
        raise ValueError(f"Unknown item id {item_id}")

    new_qty = item.qty_on_hand + delta
    if new_qty < 0:
        raise ValueError(f"Insufficient stock for item {item_id}: {new_qty}")
    item.qty_on_hand = new_qty
    db.commit()
