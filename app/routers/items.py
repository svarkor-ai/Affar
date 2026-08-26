"""Catalog router (contract C8) — HTTP surface for items.

    POST /api/items            ItemIn -> ItemOut   [admin, sales, finance, procurement]
    GET  /api/items?active=1   -> list[ItemOut]
    GET  /api/items/{id}       -> ItemOut
    PUT  /api/items/{id}       ItemIn -> ItemOut

All item endpoints are role-gated to the C8 set — the customer role never
touches the internal catalog. ``qty_on_hand`` is NEVER mutated here; that is
the sole job of ``catalog.adjust_stock`` (I2, C8), called only by the
order/purchase services on stock in/out.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.item import ItemIn, ItemOut

from app.services import catalog  # internal service — owns qty_on_hand

# C8 allowed roles for the catalog surface. Customer is deliberately absent.
ITEM_ROLES = ["admin", "sales", "finance", "procurement"]

router = APIRouter(prefix="/api/items", tags=["items"])


@router.post("", response_model=ItemOut)
def create_item(
    body: ItemIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ITEM_ROLES)),
) -> ItemOut:
    item = catalog.create_item(db, body)
    return ItemOut(**catalog_item_to_dict(item))


@router.get("", response_model=list[ItemOut])
def list_items(
    active: bool | None = Query(default=None),
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ITEM_ROLES)),
) -> list[ItemOut]:
    items = catalog.list_items(db, active_only=active)
    return [ItemOut(**catalog_item_to_dict(i)) for i in items]


@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ITEM_ROLES)),
) -> ItemOut:
    item = catalog.get_item_or_404(db, item_id)
    return ItemOut(**catalog_item_to_dict(item))


@router.put("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int,
    body: ItemIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ITEM_ROLES)),
) -> ItemOut:
    item = catalog.update_item(db, item_id, body)
    return ItemOut(**catalog_item_to_dict(item))


def catalog_item_to_dict(item) -> dict:
    """Project an ORM Item onto the ItemOut field set (avoids bare ORM exposure)."""
    return {
        "id": item.id,
        "sku": item.sku,
        "name": item.name,
        "description": item.description,
        "unit_price": item.unit_price,
        "qty_on_hand": item.qty_on_hand,
        "active": item.active,
    }
