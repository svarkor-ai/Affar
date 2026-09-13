"""Payment wire schemas (contract C17, rev-2 — Decimal pinned on the wire).

PaymentIn.amount is constrained in the schema: gt=0, max_digits=12,
decimal_places=2 (rev-2, refutation 4). Payments are a SIMULATED record (I3) —
no external gateway. ``method`` is a closed set from the model.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.finance import PAYMENT_METHODS
from app.schemas.money import money_comma_validator


class PaymentIn(BaseModel):
    """POST /api/invoices/{id}/payment body."""

    # MC 1182.6: accept Swedish comma decimals ("10,50") on the wire.
    _accept_comma_decimals = money_comma_validator("amount")

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: str = Field(
        min_length=1,
        max_length=20,
        description="One of: bank, cash, card",
        pattern="^(bank|cash|card)$",
    )
    date: Optional[datetime] = None


class PaymentOut(BaseModel):
    """Payment representation on the wire."""

    id: int
    invoice_id: int
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    method: str
    paid_at: datetime
    # MC 1175.3: non-null on a refund row — the id of the makulerad payment.
    cancels_payment_id: Optional[int] = None
