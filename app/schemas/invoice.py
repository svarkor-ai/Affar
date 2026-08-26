"""Invoice wire schemas (contract C16 / C23).

InvoiceOut carries the lines (copied from the order at issue) and the recorded
payments, plus the paid/issued timestamps. Every money field is Decimal with
max_digits=12, decimal_places=2 (I3 / C23). The wire never carries unit_price
from a client — invoice lines copy the order's already-snapshotted values.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.payment import PaymentOut


class InvoiceStatusIn(BaseModel):
    """PATCH /api/invoices/{id}/status body — forward lifecycle move."""

    status: str = Field(
        min_length=1,
        max_length=20,
        description="One of: draft, issued, paid (C15 closed set)",
        pattern="^(draft|issued|paid)$",
    )


class InvoiceLineOut(BaseModel):
    """One line of an issued invoice (server-owned snapshot, C16)."""

    id: int
    item_id: Optional[int] = None
    description: str
    qty: int
    unit_price: Decimal = Field(max_digits=12, decimal_places=2)
    line_total: Decimal = Field(max_digits=12, decimal_places=2)


class InvoiceOut(BaseModel):
    """Invoice representation on the wire — never a raw ORM object (C16)."""

    id: int
    order_id: int
    invoice_no: str
    status: str
    total: Decimal = Field(max_digits=12, decimal_places=2)
    issued_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    lines: list[InvoiceLineOut] = []
    payments: list[PaymentOut] = []
