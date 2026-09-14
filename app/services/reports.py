"""Reports service (MC 1182.9) — read-only aggregations for the dashboard.

Three reports, all pure reads (no writes, no stock moves — I2 untouched):

  monthly_sales(db, months)   -> issued+paid invoice totals grouped per month
  ar_aging(db)                -> outstanding AR per invoice bucketed 0-30/31-60/
                                 61-90/90+ days past issue
  stock_balance(db)           -> qty_on_hand + inventory value per item

All money arithmetic runs on Decimal (rev-2, refutation 4); every sum is
quantized to 0.01 before it leaves the service. Cancelled invoices are
excluded everywhere (makulering is terminal, MC 1175.2) — a cancelled
invoice is not a sale and not a receivable.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Invoice, Item

_TWO_PLACES = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    """Quantize a Decimal sum to 12,2 (the wire money shape, I3)."""
    return Decimal(value).quantize(_TWO_PLACES)


def monthly_sales(db: Session, months: int = 12) -> list[dict]:
    """Issued+paid invoice totals grouped per calendar month, oldest first.

    The month key is taken from ``issued_at`` (the sale date); an invoice
    without issued_at (a draft) contributes nothing. Returns exactly
    *months* buckets, zero-filled, so the frontend can plot a straight
    series without gaps.
    """
    months = max(1, min(months, 24))
    now = datetime.now(UTC)
    # First day of the current month, UTC.
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Oldest bucket start = first day of (months-1) months back.
    oldest = month_start
    for _ in range(months - 1):
        oldest = (oldest - timedelta(days=1)).replace(day=1)

    buckets: dict[str, Decimal] = {}
    keys: list[str] = []
    cursor = oldest
    for _ in range(months):
        key = cursor.strftime("%Y-%m")
        buckets[key] = Decimal("0.00")
        keys.append(key)
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    rows = (
        db.query(Invoice.issued_at, Invoice.total)
        .filter(Invoice.status.in_(("issued", "paid")))
        .all()
    )
    for issued_at, total in rows:
        if issued_at is None:
            continue
        key = issued_at.astimezone(UTC).strftime("%Y-%m")
        if key in buckets:
            buckets[key] += Decimal(total)

    return [
        {"month": key, "total": _q(buckets[key])}
        for key in keys
    ]


def ar_aging(db: Session) -> dict:
    """Accounts-receivable aging for issued (unpaid) invoices.

    Outstanding = total - net recorded payments (makulering refund rows are
    negative, so the net is already correct). Buckets are days PAST ISSUE:
    current (0-30), 31-60, 61-90, 90+. Cancelled invoices are excluded.
    """
    today = datetime.now(UTC)
    buckets = {
        "0-30": Decimal("0.00"),
        "31-60": Decimal("0.00"),
        "61-90": Decimal("0.00"),
        "90+": Decimal("0.00"),
    }
    rows_out: list[dict] = []

    invoices = (
        db.query(Invoice)
        .filter(Invoice.status == "issued")
        .order_by(Invoice.issued_at.asc())
        .all()
    )
    for inv in invoices:
        net_paid = sum((p.amount for p in inv.payments), Decimal("0.00"))
        outstanding = Decimal(inv.total) - net_paid
        if outstanding <= 0:
            continue  # overpaid/covered but not yet reconciled — not AR
        if inv.issued_at is None:
            days = 0
        else:
            days = (today - inv.issued_at.astimezone(UTC)).days
        if days <= 30:
            bucket = "0-30"
        elif days <= 60:
            bucket = "31-60"
        elif days <= 90:
            bucket = "61-90"
        else:
            bucket = "90+"
        buckets[bucket] += outstanding
        rows_out.append(
            {
                "invoice_id": inv.id,
                "invoice_no": inv.invoice_no,
                "issued_at": inv.issued_at.astimezone(UTC).isoformat(),
                "days_overdue": days,
                "outstanding": _q(outstanding),
            }
        )

    return {
        "buckets": {k: _q(v) for k, v in buckets.items()},
        "total_outstanding": _q(sum(buckets.values(), Decimal("0.00"))),
        "invoices": rows_out,
    }


def stock_balance(db: Session) -> dict:
    """Inventory balance per item: qty_on_hand and value at unit_price.

    Read-only over the catalog (I2: qty_on_hand is the single stock owner);
    includes inactive items (they still hold stock) but flags them.
    """
    items = db.query(Item).order_by(Item.sku.asc()).all()
    rows = []
    total_value = Decimal("0.00")
    for it in items:
        value = (Decimal(it.qty_on_hand) * Decimal(it.unit_price)).quantize(
            _TWO_PLACES
        )
        total_value += value
        rows.append(
            {
                "item_id": it.id,
                "sku": it.sku,
                "name": it.name,
                "qty_on_hand": it.qty_on_hand,
                "unit_price": _q(it.unit_price),
                "stock_value": value,
                "active": it.active,
            }
        )
    return {
        "items": rows,
        "total_value": _q(total_value),
    }
