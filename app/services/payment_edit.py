"""Payment edit service (MC 1175.3) — makulering av felaktig betalning.

Split from services.payments (C17) so that module keeps its one concern
(record/reconcile/list). One rule lives here:

* ``cancel_payment`` — makulering of a single recorded payment. Payments are
  an APPEND-ONLY ledger (I3, simulated money): a wrong payment is never
  deleted or edited, it is OFFSET by a linked negative refund row (amount < 0,
  same method) whose ``cancels_payment_id`` points at the original. Both rows
  stay; the pair nets to zero.

An invoice's NET money is sum(all payment amounts incl. refunds), so
``payments._paid_so_far`` and the T2 invoice-edit path already account for
refunds. When a refund drops the net below the invoice total, the invoice
falls back from "paid" to "issued" (unsettled) and ``paid_at`` clears —
otherwise the paid flag would silently outlive the money behind it.

Guards (each verified in tests/test_payments_edit_1175.py):
  unknown payment -> 404; already-makulerad original -> 409 (idempotency
  guard); refund row (amount < 0) is not cancellable -> 409; cancelled
  invoice is terminal -> 410 (mirrors T2); roles [admin, finance] (C17).
"""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Payment


def cancel_payment(db: Session, payment_id: int) -> Payment:
    """Makulera one recorded payment by appending its negative counterpart.

    Returns the created refund Payment row (amount = -original.amount,
    same method, ``cancels_payment_id`` = original id).
    """
    original = db.get(Payment, payment_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    # A refund row is itself a makulering — it is never cancellable.
    if original.amount < 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Payment {payment_id} is a refund; refunds cannot be makulerad",
        )
    # Idempotency guard: one makulering per payment (follow the back-link).
    already = (
        db.query(Payment)
        .filter(Payment.cancels_payment_id == payment_id)
        .first()
    )
    if already is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Payment {payment_id} is already makulerad (refund {already.id})",
        )

    invoice = original.invoice
    if invoice.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Invoice {invoice.id} is cancelled; payments are not accepted",
        )

    refund = Payment(
        invoice_id=invoice.id,
        amount=(-original.amount).quantize(Decimal("0.01")),
        method=original.method,
        cancels_payment_id=original.id,
    )
    db.add(refund)
    db.flush()  # both rows now present so _paid_so_far sees the net

    # Net fell below the total -> the invoice is no longer settled.
    from app.services.payments import _paid_so_far

    if invoice.status == "paid" and _paid_so_far(invoice) < invoice.total:
        invoice.status = "issued"
        invoice.paid_at = None

    db.commit()
    db.refresh(refund)
    return refund
