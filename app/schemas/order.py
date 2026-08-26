"""Order wire schemas (contract C13 rev-2 / C14).

C13 rev-2: the wire carries only ``{item_id, qty}`` for each line. ``unit_price``
is NOT accepted from the client — it is snapshotted server-side from the Item in
the service layer. C23: every money field the server exposes is Decimal with
max_digits=12, decimal_places=2 and an explicit bound where the wire supplies it
(here the snapshot price and computed subtotal are non-negative).
"""

from decimal import Decimal

from pydantic import BaseModel, Field


class OrderLineIn(BaseModel):
    """A single line on the wire — only {item_id, qty} (C13 rev-2)."""

    item_id: int = Field(gt=0)
    qty: int = Field(ge=1)


class OrderIn(BaseModel):
    """POST /api/orders body.

    ``customer_id`` references the Customer aggregate; ``lines`` must be
    non-empty (an order with no lines is not an order). ``unit_price`` is never
    supplied here — the server snapshots it from the Item at creation (C14).
    """

    customer_id: int = Field(gt=0)
    lines: list[OrderLineIn] = Field(min_length=1)


class OrderLineOut(BaseModel):
    """A line as returned on the wire — includes the snapshotted prices."""

    id: int
    item_id: int
    qty: int
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    subtotal: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class OrderOut(BaseModel):
    """Order representation on the wire — never a raw ORM object.

    ``total`` is the server-summed line subtotals; ``status`` is one of the
    closed ORDER_STATUS set. ``tracking_ref`` is staff-only and not surfaced on
    the public order read (rev-2 / C20).
    """

    id: int
    customer_id: int
    status: str
    total: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    created_at: str
    lines: list[OrderLineOut]
