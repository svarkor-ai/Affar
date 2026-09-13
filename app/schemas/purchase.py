"""Purchase-order wire schemas (C18/C19 + C23).

C23 pins every money field to Decimal: PurchaseOrderLineIn.unit_cost is
Decimal, ge=0, max_digits=12, decimal_places=2 (rev-2, C19); qty > 0.
line_total is computed SERVER-SIDE by the service from the validated values —
never taken from the wire. Everything the router returns is a schema object,
never a raw ORM object.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import money_comma_validator


class PurchaseOrderLineIn(BaseModel):
    """A single line on the wire when creating a PO (C19).

    extra="forbid" (MC 1175.4): a PATCH body is validated against this schema
    too, so a client-supplied status/total on a line is a 422, never stored.
    unit_cost stays wire-supplied on the purchase side (C18 — negotiated per
    supplier) but bounded exactly as at creation.
    """

    model_config = ConfigDict(extra="forbid")

    # MC 1182.6: accept Swedish comma decimals ("10,50") on the wire.
    _accept_comma_decimals = money_comma_validator("unit_cost")

    item_id: int = Field(gt=0)
    qty: int = Field(gt=0)
    # Negotiated per-supplier cost — legitimately PO-scoped (C18). Bounded:
    # Decimal, non-negative (refutation 1 purchase-side fix), (12,2).
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PurchaseOrderIn(BaseModel):
    """POST /api/purchase-orders body (C19)."""

    supplier_id: int = Field(gt=0)
    lines: list[PurchaseOrderLineIn] = Field(min_length=1)


class PurchaseOrderLineOut(BaseModel):
    """PO line representation on the wire (server-computed money)."""

    id: int
    item_id: int
    qty: int
    unit_cost: Decimal = Field(max_digits=12, decimal_places=2)
    line_total: Decimal = Field(max_digits=12, decimal_places=2)


class PurchaseOrderOut(BaseModel):
    """PurchaseOrder representation on the wire — never a raw ORM object."""

    id: int
    supplier_id: int
    status: str
    lines: list[PurchaseOrderLineOut] = Field(default_factory=list)


class PurchaseOrderStatusIn(BaseModel):
    """PATCH /api/purchase-orders/{id}/status body (C19).

    MC 1175.4: ``cancel`` joins the accepted values — it is makulering, not a
    lifecycle move, and is routed out in the service (never ranked in the
    forward lifecycle). The service still owns the live transition rules.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1)


class PurchaseOrderPatch(BaseModel):
    """PATCH /api/purchase-orders/{id} body — MC 1175.4 draft line edit.

    ``lines`` REPLACES the whole line set (remove/add/change qty/cost in one
    call). Only a draft is editable server-side; line_total is recomputed
    server-side, and ``extra="forbid"`` rejects any smuggled status/total.
    """

    model_config = ConfigDict(extra="forbid")

    lines: list[PurchaseOrderLineIn] = Field(min_length=1)
