"""Report wire schemas (MC 1182.9, contract C23 — never a raw ORM object).

All money fields are Decimal with max_digits=12, decimal_places=2 (I3).
Read-only outputs; there are no In-schemas — the reports accept no body.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class MonthlySalesRow(BaseModel):
    """One month bucket of issued+paid sales."""

    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    total: Decimal = Field(max_digits=12, decimal_places=2)


class ArAgingInvoice(BaseModel):
    """One outstanding issued invoice in the AR-aging detail list."""

    invoice_id: int
    invoice_no: str
    issued_at: datetime
    days_overdue: int
    outstanding: Decimal = Field(max_digits=12, decimal_places=2)


class ArAgingOut(BaseModel):
    """AR-aging report: per-bucket totals + the detail rows behind them."""

    buckets: dict[str, Decimal] = Field(
        description="Bucket key (0-30, 31-60, 61-90, 90+) -> outstanding total"
    )
    total_outstanding: Decimal = Field(max_digits=12, decimal_places=2)
    invoices: list[ArAgingInvoice] = []


class StockBalanceRow(BaseModel):
    """One item's stock balance and value."""

    item_id: int
    sku: str
    name: str
    qty_on_hand: int
    unit_price: Decimal = Field(max_digits=12, decimal_places=2)
    stock_value: Decimal = Field(max_digits=12, decimal_places=2)
    active: bool


class StockBalanceOut(BaseModel):
    """Stock-balance report: per-item rows + the inventory total value."""

    items: list[StockBalanceRow] = []
    total_value: Decimal = Field(max_digits=12, decimal_places=2)
