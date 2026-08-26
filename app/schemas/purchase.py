"""Purchase-order wire schemas (C18/C19 + C23).

C23 pins every money field to Decimal: PurchaseOrderLineIn.unit_cost is
Decimal, ge=0, max_digits=12, decimal_places=2 (rev-2, C19); qty > 0.
line_total is computed SERVER-SIDE by the service from the validated values —
never taken from the wire. Everything the router returns is a schema object,
never a raw ORM object.
"""

from decimal import Decimal

from pydantic import BaseModel, Field


class PurchaseOrderLineIn(BaseModel):
    """A single line on the wire when creating a PO (C19)."""

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
    """PATCH /api/purchase-orders/{id}/status body (C19)."""

    status: str = Field(min_length=1)
