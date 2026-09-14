"""Reports router (MC 1182.9) — HTTP surface for the dashboard reports.

    GET /api/reports/monthly-sales?months=N -> list[MonthlySalesRow]  [admin, finance]
    GET /api/reports/ar-aging               -> ArAgingOut             [admin, finance]
    GET /api/reports/stock-balance          -> StockBalanceOut        [admin, procurement]

All three are pure reads (no writes, no stock moves). Role gates follow the
module ownership: sales/finance numbers are finance+admin, stock is
procurement+admin. Returns schema objects (C23), never raw ORM.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.report import (
    ArAgingOut,
    MonthlySalesRow,
    StockBalanceOut,
)

from app.services import reports as svc

router = APIRouter(prefix="/api/reports", tags=["reports"])

SALES_ROLES = ["admin", "finance"]
STOCK_ROLES = ["admin", "procurement"]


@router.get("/monthly-sales", response_model=list[MonthlySalesRow])
def monthly_sales(
    months: int = Query(default=12, ge=1, le=24),
    db: Session = Depends(get_session),
    _auth=Depends(require_role(SALES_ROLES)),
) -> list[MonthlySalesRow]:
    """Issued+paid invoice totals per calendar month, oldest first."""
    return [
        MonthlySalesRow(**row) for row in svc.monthly_sales(db, months=months)
    ]


@router.get("/ar-aging", response_model=ArAgingOut)
def ar_aging(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(SALES_ROLES)),
) -> ArAgingOut:
    """Outstanding AR per aging bucket (days past issue) + detail rows."""
    return ArAgingOut(**svc.ar_aging(db))


@router.get("/stock-balance", response_model=StockBalanceOut)
def stock_balance(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(STOCK_ROLES)),
) -> StockBalanceOut:
    """Per-item qty_on_hand + inventory value at unit_price."""
    return StockBalanceOut(**svc.stock_balance(db))
