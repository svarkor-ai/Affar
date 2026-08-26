"""Payments service (contract C17) — simulated payment recording.

Payments are a SIMULATED record (I3): no external gateway. A Payment row holds
an amount, a method from the closed set {bank, cash, card}, and a paid_at. All
money arithmetic runs on Decimal (rev-2, refutation 4): the wire amount is
constrained gt=0 / max_digits=12 / decimal_places=2, columns are Numeric(12,2),
and the cover check ``sum(payments) >= invoice.total`` compares Decimals.

Recording a payment marks the invoice paid as soon as the accumulated sum
reaches the total (C17: "marks invoice paid when sum(payments) >= invoice.total",
all Decimal math). Reconcile is the explicit recheck endpoint: it sets
status="paid" when covered, else raises 409 "still outstanding".

Stock single-owner (I2) and catalog are untouched here — payments only affect
the invoice/payment tables.
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Invoice, Payment
from app.models.finance import PAYMENT_METHODS
from app.services.invoicing import get_invoice_or_404

# Same staff set as invoicing (C17 lists [admin, finance]).
PAYMENT_ROLES = ["admin", "finance"]


def _paid_so_far(invoice: Invoice) -> Decimal:
    """Return the sum of all recorded payment amounts for *invoice* (Decimal)."""
    return sum((p.amount for p in invoice.payments), Decimal("0.00"))


def record_payment(
    db: Session, invoice_id: int, amount: Decimal, method: str,
    paid_at: datetime | None = None,
) -> Payment:
    """Record a payment against an invoice; auto-mark paid when covered (C17).

    *amount* is a Decimal already validated by the schema (gt=0, 12,2). Only a
    known method is accepted (422). Returns the created Payment row.
    """
    invoice = get_invoice_or_404(db, invoice_id)

    if method not in PAYMENT_METHODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown payment method {method!r}; must be one of {PAYMENT_METHODS}",
        )

    payment = Payment(
        invoice_id=invoice.id,
        amount=amount.quantize(Decimal("0.01")),
        method=method,
        paid_at=paid_at or datetime.now(UTC),
    )
    db.add(payment)
    db.flush()

    # Cover check on Decimals: sum(payments) >= invoice.total -> paid.
    if _paid_so_far(invoice) >= invoice.total:
        invoice.status = "paid"
        invoice.paid_at = invoice.paid_at or datetime.now(UTC)

    db.commit()
    db.refresh(payment)
    return payment


def reconcile(db: Session, invoice_id: int) -> Invoice:
    """Recheck coverage: set paid when covered, else 409 "still outstanding".

    Idempotent for an already-paid invoice (covered -> stays paid, 200).
    """
    invoice = get_invoice_or_404(db, invoice_id)

    if _paid_so_far(invoice) >= invoice.total:
        if invoice.status != "paid":
            invoice.status = "paid"
            invoice.paid_at = datetime.now(UTC)
            db.commit()
            db.refresh(invoice)
        return invoice

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Invoice {invoice_id} still outstanding: "
               f"{_paid_so_far(invoice)} paid of {invoice.total}",
    )


def list_payments(db: Session) -> list[Payment]:
    """Return all recorded payments, newest first."""
    return (
        db.query(Payment)
        .order_by(Payment.id.desc())
        .all()
    )
