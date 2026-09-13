"""Item wire schemas (C7/C8 + C23).

One Pydantic model set for the catalog aggregate.

C23: every money field is Decimal with max_digits=12, decimal_places=2 and an
explicit bound where the wire supplies it — ItemIn.unit_price is `ge=0` (the
catalog price never goes negative). Routers return schema objects, never raw
ORM objects.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.money import money_comma_validator


class ItemIn(BaseModel):
    """POST/PUT /api/items body."""

    # MC 1182.6: accept Swedish comma decimals ("10,50") on the wire.
    _accept_comma_decimals = money_comma_validator("unit_price")

    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    qty_on_hand: int = Field(default=0, ge=0)


class ItemOut(BaseModel):
    """Item representation on the wire — never a raw ORM object."""

    id: int
    sku: str
    name: str
    description: Optional[str] = None
    unit_price: Decimal = Field(max_digits=12, decimal_places=2)
    qty_on_hand: int
    active: bool = True
    # MC 1175.5: unified activation name across items/customers/suppliers.
    # C8 keeps `active` on the wire for backward compatibility — both carry
    # the same value (see routers.items.catalog_item_to_dict).
    is_active: bool = True
