"""Invoice edit service (MC 1175.2) — rättning + makulering rules.

Split from services.invoicing (C16) so that module keeps its one concern
(issue/list/lifecycle). Two rules live here:

* ``replace_invoice_lines`` — a NOT-YET-PAID invoice's line set can be
  replaced. Prices are never client-supplied (C14): they carry over per
  item_id from the old server-owned lines (an invoice never re-prices, C16);
  a new item_id takes the Item's catalog price at correction time, and a
  free (description-only) line keeps the price of the old free line with the
  same description, else 0.00. A PAID invoice is 409 — money is settled and
  a line edit would silently break the sum(payments) >= total cover rule
  (C17); its correction path is payments (T3). CANCELLED is 410 (terminal).

* ``cancel_invoice`` — makulering. Terminal, OUTSIDE the forward lifecycle
  draft -> issued -> paid. Refund-before-void: cancelled implies
  sum(payments) == 0.00, so finance cancels the wrong payments FIRST
  (T3: payment cancellation) and the invoice second. A cancelled invoice
  rejects edits, lifecycle re-entry (410) and new payments (payments router).
"""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine, Item
from app.services.invoicing import get_invoice_or_404


def replace_invoice_lines(db: Session, invoice_id: int, lines) -> Invoice:
    """MC 1175.2 — replace the line set of a NOT-YET-PAID invoice (rättning).

    ``lines`` carries {item_id?, description?, qty} only — never a price
    (C14). An unknown item id rolls the whole replacement back (404).
    """
    invoice = get_invoice_or_404(db, invoice_id)
    if invoice.status == "paid":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invoice {invoice_id} is paid; correct its money via payments "
                "(a paid invoice cannot be line-edited)"
            ),
        )
    if invoice.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Invoice {invoice_id} is cancelled; it cannot be edited",
        )

    # Price map from the OLD lines (server-owned carry-over), per item_id.
    old_prices = {
        ln.item_id: Decimal(ln.unit_price)
        for ln in invoice.lines
        if ln.item_id is not None
    }

    # Resolve new item ids once — O(n) lookups, uniform 404, atomic rollback.
    item_ids = [ln.item_id for ln in lines if ln.item_id is not None]
    item_map = {it.id: it for it in db.query(Item).filter(Item.id.in_(item_ids)).all()}

    new_lines = []
    for ln in lines:
        if ln.item_id is not None:
            item = item_map.get(ln.item_id)
            if item is None:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Item {ln.item_id} not found",
                )
            unit_price = old_prices.get(ln.item_id, Decimal(item.unit_price))
            description = ln.description or item.name
        else:
            if ln.description is None:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A free line (no item_id) needs a description",
                )
            description = ln.description
            # A removed-then-readded line keeps its old server price when the
            # invoice copied it (same description); a new free line starts at 0.
            unit_price = next(
                (
                    Decimal(old.unit_price)
                    for old in invoice.lines
                    if old.item_id is None and old.description == ln.description
                ),
                Decimal("0.00"),
            )
        line_total = (Decimal(ln.qty) * unit_price).quantize(Decimal("0.01"))
        new_lines.append(
            InvoiceLine(
                item_id=ln.item_id,
                description=description,
                qty=ln.qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    # delete-orphan cascade drops the old rows when the collection is cleared.
    invoice.lines.clear()
    invoice.lines.extend(new_lines)
    invoice.total = sum(
        (ln.line_total for ln in new_lines), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    db.commit()
    db.refresh(invoice)
    return invoice


def cancel_invoice(db: Session, invoice_id: int) -> Invoice:
    """MC 1175.2 — makulera a fully refunded invoice (terminal).

    Refund-before-void rule: a cancelled invoice must carry
    sum(payments) == 0.00, so finance cancels the wrong payments FIRST
    (T3) and the invoice second. Cancelled is terminal: 409 on re-cancel,
    410 on edit/lifecycle re-entry (invoicing module), 409 on new payment
    (payments router).
    """
    invoice = get_invoice_or_404(db, invoice_id)
    if invoice.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invoice {invoice_id} is already cancelled",
        )
    refunds = sum((p.amount for p in invoice.payments), Decimal("0.00"))
    if refunds != Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invoice {invoice_id} still has {refunds} in net payments; "
                "cancel its payments before makulering it (makulering kräver "
                "belopp ligger ovanif)"
            ),
        )
    invoice.status = "cancelled"
    db.commit()
    db.refresh(invoice)
    return invoice
