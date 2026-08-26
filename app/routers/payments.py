"""Payments router (contract C17) — HTTP surface for payments.

    POST   /api/invoices/{id}/payment   PaymentIn -> PaymentOut  [admin, finance]
    POST   /api/invoices/{id}/reconcile -> InvoiceOut            [admin, finance]
    GET    /api/payments                -> list[PaymentOut]

Recording is simulated (I3) — no gateway. The amount is validated in the schema
(gt=0, 12,2) so the service always sees a Decimal. Reconcile reuses the invoice
projection so the response shape matches C16's InvoiceOut.
"""

from datetime import UTC
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.payment import PaymentIn, PaymentOut
from app.schemas.invoice import InvoiceOut

from app.services import payments as svc
from app.routers.invoices import _invoice_to_out

router = APIRouter(prefix="/api", tags=["payments"])


@router.post("/invoices/{invoice_id}/payment", response_model=PaymentOut)
def create_payment(
    invoice_id: int,
    body: PaymentIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(svc.PAYMENT_ROLES)),
) -> PaymentOut:
    payment = svc.record_payment(
        db, invoice_id, body.amount, body.method, body.date
    )
    return PaymentOut(
        id=payment.id,
        invoice_id=payment.invoice_id,
        amount=Decimal(payment.amount).quantize(Decimal("0.01")),
        method=payment.method,
        paid_at=payment.paid_at.astimezone(UTC).isoformat(),
    )


@router.post("/invoices/{invoice_id}/reconcile", response_model=InvoiceOut)
def reconcile(
    invoice_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(svc.PAYMENT_ROLES)),
):
    invoice = svc.reconcile(db, invoice_id)
    return _invoice_to_out(invoice)


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(svc.PAYMENT_ROLES)),
) -> list[PaymentOut]:
    return [
        PaymentOut(
            id=p.id,
            invoice_id=p.invoice_id,
            amount=Decimal(p.amount).quantize(Decimal("0.01")),
            method=p.method,
            paid_at=p.paid_at.astimezone(UTC).isoformat(),
        )
        for p in svc.list_payments(db)
    ]
