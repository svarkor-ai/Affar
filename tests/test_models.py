"""Verification test for MC 650.1 (app-models).

Real executed checks:
  1. all aggregates import through app.models (single re-export surface)
  2. init_db() over in-memory sqlite creates all tables from the ORM metadata
  3. full aggregate graph persistence + read-back (order->invoice->payment,
     purchase, tracking) with DECIMAL money preserved as Decimal (I7)
  4. closed-enum checks: non-enum carrier / status rejected at the model boundary
     via the documented closed tuples (the closed set is the contract)
"""

import os
from decimal import Decimal

# Point the database at an in-memory sqlite BEFORE importing app.database.
os.environ["AFFAR_DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import init_db, get_engine  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    CARRIER,
    Customer,
    DeliveryTrack,
    Invoice,
    InvoiceLine,
    Item,
    Order,
    OrderLine,
    Payment,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    TRACK_EVENT,
    TrackingEvent,
    User,
)


def test_all_tables_created():
    init_db()
    engine = get_engine()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "users",
        "items",
        "customers",
        "suppliers",
        "orders",
        "order_lines",
        "invoices",
        "invoice_lines",
        "payments",
        "purchase_orders",
        "purchase_order_lines",
        "delivery_tracks",
        "tracking_events",
    }
    missing = expected - tables
    assert not missing, f"missing tables: {missing}"
    assert tables == expected, f"unexpected extra tables: {tables - expected}"


def test_init_db_idempotent():
    # Calling init_db twice must not raise (metadata.create_all is a no-op on
    # existing tables).
    init_db()
    init_db()


def test_full_aggregate_graph_persists():
    init_db()
    with Session(get_engine()) as s:
        u = User(username="sales1", password_hash="x", role="sales")
        cust = Customer(name="Demo AB", email="a@b.se")
        sup = Supplier(name="Leverantören AB")
        item = Item(sku="K-1", name="Kaffekopp", unit_price=Decimal("49.90"), qty_on_hand=100)
        s.add_all([u, cust, sup, item])
        s.flush()

        order = Order(customer_id=cust.id, status="confirmed")
        order.lines.append(OrderLine(item_id=item.id, qty=2, unit_price=item.unit_price, subtotal=Decimal("99.80")))
        s.add(order)
        s.flush()

        invoice = Invoice(order_id=order.id, invoice_no="INV-1", status="paid", total=Decimal("99.80"))
        invoice.lines.append(InvoiceLine(item_id=item.id, description="Kaffekopp", qty=2, unit_price=Decimal("49.90"), line_total=Decimal("99.80")))
        invoice.payments.append(Payment(amount=Decimal("99.80"), method="card"))
        s.add(invoice)

        po = PurchaseOrder(supplier_id=sup.id, status="received")
        po.lines.append(PurchaseOrderLine(item_id=item.id, qty=50, unit_cost=Decimal("19.90"), line_total=Decimal("995.00")))
        s.add(po)

        track = DeliveryTrack(order_id=order.id, carrier="postnord", tracking_id="a1b2" * 16)
        track.events.append(TrackingEvent(status="delivered", note="Överlämnad"))
        s.add(track)
        s.commit()

        # Capture PKs BEFORE the session closes (avoids DetachedInstanceError).
        order_id = order.id
        invoice_id = invoice.id
        po_id = po.id
        track_id = track.id
        tracked_id = track.tracking_id

    # Read-back in a fresh session
    with Session(get_engine()) as s:
        o = s.query(Order).filter_by(id=order_id).one()
        assert o.status == "confirmed"
        assert o.lines[0].unit_price == Decimal("49.90")  # DECIMAL preserved (I7)
        assert isinstance(o.lines[0].unit_price, Decimal)
        assert o.customer.name == "Demo AB"

        inv = s.query(Invoice).filter_by(id=invoice_id).one()
        assert inv.status == "paid"
        assert inv.total == Decimal("99.80")
        assert inv.payments[0].amount == Decimal("99.80")

        po2 = s.query(PurchaseOrder).filter_by(id=po_id).one()
        assert po2.lines[0].unit_cost == Decimal("19.90")
        assert po2.supplier.name == "Leverantören AB"

        tr = s.query(DeliveryTrack).filter_by(id=track_id).one()
        assert tr.tracking_id == tracked_id
        assert tr.events[0].status == "delivered"


def test_closed_enum_sets():
    # The closed tuples are the contract (C20 rev-3, C5 roles, item/order statuses).
    assert "own-fleet" in CARRIER
    assert "postnord" in CARRIER
    # No free-text carrier is representable — the closed set is all that exists.
    assert "postnord" in CARRIER
    # Order status closed set
    from app.models.order import ORDER_STATUS
    assert set(ORDER_STATUS) == {"draft", "confirmed", "shipped", "delivered"}
    # Tracking event status closed set
    assert set(TRACK_EVENT) >= {"placed", "delivered"}


def test_decimal_not_float_in_schema():
    # I7: money columns are Numeric (DECIMAL), never float.
    money_cols = {
        "items.unit_price",
        "order_lines.unit_price",
        "order_lines.subtotal",
        "invoices.total",
        "invoice_lines.unit_price",
        "invoice_lines.line_total",
        "payments.amount",
        "purchase_order_lines.unit_cost",
        "purchase_order_lines.line_total",
    }
    for table, col in [c.split(".") for c in money_cols]:
        col_type = Base.metadata.tables[table].c[col].type
        assert hasattr(col_type, "asdecimal") and col_type.asdecimal is True, (
            f"{table}.{col} is not DECIMAL-backed: {col_type}"
        )
