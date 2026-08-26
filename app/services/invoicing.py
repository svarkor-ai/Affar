"""Invoicing service (contract C16) — business rules for invoices.

An invoice is created ONLY from a confirmed sales order (one invoice per
confirmed order, C15 unique order_id). It COPIES the order's lines as invoice
lines — description comes from the item name, qty/unit_price/line_total from
the already-snapshotted order-line values (C14; the invoice never re-prices).
total = sum(line_total), all Decimal.

Lifecycle (C16): draft -> issued -> paid. Creating from a confirmed order
issues immediately (status="issued"). Status transitions are forward-only and
validated against the closed set (C15: draft, issued, paid); any backward or
invalid move is rejected.

Stock single-owner (I2) is untouched here — issue only records, never moves
qty. Payments/reconcile live in services.payments (C17).
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine, Order
from app.models.finance import INVOICE_STATUS

# Staff who issue and manage invoices. Payments/reconcile share this set (C17).
INVOICE_ROLES = ["admin", "finance"]


def get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    """Return the invoice with *invoice_id* or raise 404."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    return invoice


def create_invoice_from_order(db: Session, order_id: int) -> Invoice:
    """Issue an invoice for a confirmed order, copying its lines (C16).

    Raises 404 when the order is missing or not yet confirmed; 409 when an
    invoice already exists for the order (one per confirmed order, C15).
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    if order.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order is not confirmed; only a confirmed order can be invoiced",
        )

    existing = db.query(Invoice).filter(Invoice.order_id == order_id).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invoice already exists for this order",
        )

    invoice = Invoice(
        order_id=order.id,
        invoice_no=f"INV-{order.id}-{datetime.now(UTC).strftime('%Y%m%d')}",
        status="issued",
        total=Decimal("0.00"),
        issued_at=datetime.now(UTC),
    )
    db.add(invoice)
    db.flush()

    # Copy each order line as an invoice line; total = sum of line_totals.
    running_total = Decimal("0.00")
    for ol in order.lines:
        line_total = (Decimal(ol.qty) * Decimal(ol.unit_price)).quantize(
            Decimal("0.01")
        )
        running_total += line_total
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                item_id=ol.item_id,
                description=ol.item.name if ol.item is not None else f"Item {ol.item_id}",
                qty=ol.qty,
                unit_price=Decimal(ol.unit_price),
                line_total=line_total,
            )
        )

    invoice.total = running_total.quantize(Decimal("0.01"))
    db.commit()
    db.refresh(invoice)
    return invoice


def list_invoices(db: Session) -> list[Invoice]:
    """Return all invoices, newest first."""
    return (
        db.query(Invoice)
        .order_by(Invoice.id.desc())
        .all()
    )


def update_status(db: Session, invoice_id: int, new_status: str) -> Invoice:
    """Advance the invoice lifecycle: draft -> issued -> paid.

    Rejects values outside the closed set (422-style via HTTPException 422 is
    handled by the schema; here we 400 on an unknown status and 409 on an
    invalid/backward transition).
    """
    invoice = get_invoice_or_404(db, invoice_id)

    if new_status not in INVOICE_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown invoice status {new_status!r}; must be one of {INVOICE_STATUS}",
        )

    order = list(INVOICE_STATUS).index(new_status)
    current = list(INVOICE_STATUS).index(invoice.status)
    if order < current:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot move invoice {invoice_id} from "
                f"{invoice.status!r} back to {new_status!r}"
            ),
        )

    invoice.status = new_status
    if new_status == "paid":
        invoice.paid_at = datetime.now(UTC)
    db.commit()
    db.refresh(invoice)
    return invoice
