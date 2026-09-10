"""Invoice wire schemas (contract C16 / C23).

InvoiceOut carries the lines (copied from the order at issue) and the recorded
payments, plus the paid/issued timestamps. Every money field is Decimal with
max_digits=12, decimal_places=2 (I3 / C23). The wire never carries unit_price
from a client — invoice lines copy the order's already-snapshotted values.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.payment import PaymentOut


class InvoiceStatusIn(BaseModel):
    """PATCH /api/invoices/{id}/status body — forward lifecycle move.

    MC 1175.2: "cancel" (makulering) is accepted here, but it is NOT a
    lifecycle move — the service routes it to cancel_invoice, which refuses
    anything but a fully refunded (belopp ligger ovanif) invoice.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(
        min_length=1,
        max_length=20,
        description="One of: draft, issued, paid (C15 closed set) or cancel (MC 1175.2)",
        pattern="^(draft|issued|paid|cancel)$",
    )


class InvoiceLinePatch(BaseModel):
    """One corrected line on PATCH /api/invoices/{id} — MC 1175.2.

    extra="forbid": a client may correct {item_id?, description?, qty};
    unit_price is never on the wire (C14 holds through the correction path).
    """

    model_config = ConfigDict(extra="forbid")

    item_id: Optional[int] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, min_length=1, max_length=500)
    qty: int = Field(ge=1)


class InvoicePatch(BaseModel):
    """PATCH /api/invoices/{id} body — MC 1175.2 rättningsbara rader.

    ``lines`` REPLACES the whole line set (remove/add/correct qty in one
    call). Unit prices stay server-owned: they carry over per item_id, else
    fall back to the item's catalog price at correction time.
    """

    model_config = ConfigDict(extra="forbid")

    lines: list[InvoiceLinePatch] = Field(min_length=1)


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
