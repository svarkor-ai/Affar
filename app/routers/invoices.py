"""Invoicing routers (contract C16) — HTTP surface for invoices.

    POST   /api/orders/{id}/invoice  -> InvoiceOut   [admin, finance]
    GET    /api/invoices             -> list[InvoiceOut]
    GET    /api/invoices/{id}        -> InvoiceOut (with lines + payments)
    PATCH  /api/invoices/{id}/status {status} -> InvoiceOut

This surface only projects ORM rows onto InvoiceOut — it never returns raw ORM
objects. Issue (create from confirmed order) and status transitions live in the
service layer; payments/reconcile are the C17 router under /api/invoices/{id}/.
"""

from datetime import UTC
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.models import Invoice
from app.schemas.invoice import InvoiceOut, InvoiceStatusIn

from app.services import invoicing as svc

router = APIRouter(prefix="/api", tags=["invoices"])


@router.post("/orders/{order_id}/invoice", response_model=InvoiceOut)
def create_invoice(
    order_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(svc.INVOICE_ROLES)),
) -> InvoiceOut:
    invoice = svc.create_invoice_from_order(db, order_id)
    return _invoice_to_out(invoice)


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(svc.INVOICE_ROLES)),
) -> list[InvoiceOut]:
    return [_invoice_to_out(i) for i in svc.list_invoices(db)]


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(svc.INVOICE_ROLES)),
) -> InvoiceOut:
    invoice = svc.get_invoice_or_404(db, invoice_id)
    return _invoice_to_out(invoice)


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceOut)
def patch_status(
    invoice_id: int,
    body: InvoiceStatusIn,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(svc.INVOICE_ROLES)),
) -> InvoiceOut:
    invoice = svc.update_status(db, invoice_id, body.status)
    return _invoice_to_out(invoice)


def _invoice_to_out(invoice: Invoice) -> InvoiceOut:
    """Project an ORM Invoice (with loaded lines + payments) onto the wire set.

    total is the server-stored Decimal; timestamps converted to UTC ISO.
    """
    return InvoiceOut(
        id=invoice.id,
        order_id=invoice.order_id,
        invoice_no=invoice.invoice_no,
        status=invoice.status,
        total=Decimal(invoice.total).quantize(Decimal("0.01")),
        issued_at=(
            invoice.issued_at.astimezone(UTC).isoformat()
            if invoice.issued_at else None
        ),
        paid_at=(
            invoice.paid_at.astimezone(UTC).isoformat()
            if invoice.paid_at else None
        ),
        lines=[
            {
                "id": ln.id,
                "item_id": ln.item_id,
                "description": ln.description,
                "qty": ln.qty,
                "unit_price": Decimal(ln.unit_price).quantize(Decimal("0.01")),
                "line_total": Decimal(ln.line_total).quantize(Decimal("0.01")),
            }
            for ln in invoice.lines
        ],
        payments=[
            {
                "id": p.id,
                "invoice_id": p.invoice_id,
                "amount": Decimal(p.amount).quantize(Decimal("0.01")),
                "method": p.method,
                "paid_at": p.paid_at.astimezone(UTC).isoformat(),
            }
            for p in invoice.payments
        ],
    )
