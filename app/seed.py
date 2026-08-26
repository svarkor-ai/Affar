"""Idempotent first-boot demo seed (contract C22).

The app's ``init_db()`` creates empty tables; on a fresh deploy there would be
nothing for the demo to show. ``seed_if_empty`` populates a small, entirely
fictional (I4 scope-guard) dataset so the ERP is demonstrable out of the box:
an admin, one user per business role, a customer + a supplier, a few catalog
items, one *complete* happy-path order flow (order -> invoice -> payment +
delivery track) and one purchase order.

Idempotency: if the ``users`` table is already non-empty the seed is a no-op,
so re-running startup never duplicates demo rows nor clobbers real ones.

Demo passwords — DEMO ONLY, NOT SECRETS (per C22). Every seeded account uses a
weak, public, documented password intended purely for demos/locals. No seeded
hash is derived from anything confidential. In production these accounts are
managed (or removed) via real config + the T2 app-db-config boundary.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from secrets import token_hex

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models.customer import Customer
from app.models.finance import Invoice, InvoiceLine, Payment
from app.models.item import Item
from app.models.order import Order, OrderLine
from app.models.purchase import PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier
from app.models.tracking import CARRIER, DeliveryTrack, TrackingEvent, TRACK_EVENT
from app.models.user import User

# Demo credentials. Documented as DEMO-ONLY — trivial, public, for local/demo
# use; never a real secret. Same password across roles keeps demos low-friction.
DEMO_PASSWORDS: dict[str, str] = {
    "admin": "demo-admin-2026",
    "sales": "demo-sales-2026",
    "finance": "demo-finance-2026",
    "procurement": "demo-procurement-2026",
    "customer": "demo-customer-2026",
}

DEMO_USERS: list[tuple[str, str, str]] = [
    ("admin", "admin", "svarkor@affar.demo"),
    ("sales", "sales", "handlare@affar.demo"),
    ("finance", "finance", "ekonomi@affar.demo"),
    ("procurement", "procurement", "inkop@affar.demo"),
    ("customer", "customer", "kund@affar.demo"),
]


def seed_if_empty(db: Session) -> None:
    """Ensure the demo dataset exists; no-op when the ``users`` table is filled.

    C22 signature: ``seed_if_empty(db) -> None``, idempotent on the users table.
    """
    if db.query(User).count() > 0:
        return

    # --- Staff + customer accounts (C5) ------------------------------------
    for username, role, email in DEMO_USERS:
        db.add(
            User(
                username=username,
                password_hash=hash_password(DEMO_PASSWORDS[role]),
                role=role,
                email=email,
            )
        )
    db.flush()

    # --- Catalog (C7) + customers (C9) + suppliers (C11) -------------------
    laptop = Item(
        sku="IT-LAPTOP-14",
        name="Demo 14\" Business-Laptop",
        description="Fiktiv demo-bärbar dator (I4).",
        unit_price=Decimal("12499.00"),
        qty_on_hand=25,
        active=True,
    )
    monitor = Item(
        sku="IT-MON-27",
        name="Demo 27\" Skärm",
        description="Fiktiv demo-skärm (I4).",
        unit_price=Decimal("3499.00"),
        qty_on_hand=40,
        active=True,
    )
    chair = Item(
        sku="MO-KONTOR-STOL",
        name="Demo Kontorsstol",
        description="Fiktiv demo-kontorsstol (I4).",
        unit_price=Decimal("2450.00"),
        qty_on_hand=18,
        active=True,
    )
    keyboard = Item(
        sku="IT-TANGENTBORD",
        name="Demo Tangentbord",
        description="Fiktiv demo-tangentbord (I4).",
        unit_price=Decimal("699.00"),
        qty_on_hand=60,
        active=True,
    )
    db.add_all([laptop, monitor, chair, keyboard])
    db.flush()

    customer = Customer(
        name="Acme Fiktiv AB",
        email="kund@acme-fiktiv.example",
        phone="08-555 01 02",
        address="DemoGatan 7, 111 37 Stockholm",
    )
    supplier = Supplier(
        name="Nordic Komponenter Demo AB",
        email="order@nordic-komp.example",
        phone="031-555 30 40",
        address="Komponentvägen 3, 411 27 Göteborg",
        payment_terms="30 dagar netto",
    )
    db.add_all([customer, supplier])
    db.flush()

    # --- Buy-side happy path: one purchase order (C18) ----------------------
    po = PurchaseOrder(supplier_id=supplier.id, status="ordered")
    db.add(po)
    db.flush()
    db.add(
        PurchaseOrderLine(
            po_id=po.id,
            item_id=laptop.id,
            qty=10,
            unit_cost=Decimal("9800.00"),
            line_total=Decimal("98000.00"),
        )
    )

    # --- Complete sales happy path: order -> invoice -> payment + track -----
    order = Order(
        customer_id=customer.id,
        status="confirmed",
        tracking_ref="ORD-DEMO-1",
    )
    db.add(order)
    db.flush()

    # Order lines snapshot the catalog price (rev-2 C14) and compute subtotal
    # server-side; item: 2 x laptop + 3 x monitor.
    order_lines = [
        OrderLine(order_id=order.id, item_id=laptop.id, qty=2,
                  unit_price=laptop.unit_price, subtotal=laptop.unit_price * 2),
        OrderLine(order_id=order.id, item_id=monitor.id, qty=3,
                  unit_price=monitor.unit_price, subtotal=monitor.unit_price * 3),
    ]
    db.add_all(order_lines)
    db.flush()

    # Invoice issued + paid (full happy path C15). One per confirmed order.
    invoice_total = sum(_l.subtotal for _l in order_lines)
    invoice = Invoice(
        order_id=order.id,
        invoice_no="INV-DEMO-1",
        status="paid",
        total=invoice_total,
        issued_at=datetime.now(UTC) - timedelta(days=2),
        paid_at=datetime.now(UTC) - timedelta(hours=10),
    )
    db.add(invoice)
    db.flush()
    db.add_all(
        [
            InvoiceLine(
                invoice_id=invoice.id,
                item_id=_l.item_id,
                description=_l.item.name,
                qty=_l.qty,
                unit_price=_l.unit_price,
                line_total=_l.subtotal,
            )
            for _l in order_lines
        ]
    )
    db.add(
        Payment(
            invoice_id=invoice.id,
            amount=invoice_total,
            method="bank",
            paid_at=datetime.now(UTC) - timedelta(hours=10),
        )
    )

    # Delivery track with the full, ordered event timeline (C20). tracking_id
    # is the generated non-sequential public key (never orders.id — I5).
    track = DeliveryTrack(
        order_id=order.id,
        carrier="postnord",
        tracking_id=token_hex(16),
    )
    db.add(track)
    db.flush()
    start = datetime.now(UTC) - timedelta(hours=48)
    for i, status in enumerate(TRACK_EVENT):
        db.add(
            TrackingEvent(
                delivery_track_id=track.id,
                status=status,
                note=_staff_note(status),
                at=start + timedelta(hours=i * 8),
            )
        )

    db.commit()


def _staff_note(status: str) -> str:
    """Fictional staff free text for each demo event (staff-only surface C20)."""
    return {
        "placed": "Ordern mottagen från demo-kund.",
        "in-warehouse": "Plockas i demot-lagret.",
        "in-transit": "Skickad med postnord (demo).",
        "out-for-delivery": "På sista leveransbäraren.",
        "delivered": "Levererad till demo-kund.",
    }[status]
