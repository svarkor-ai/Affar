"""Tests for MC 650.5 (app-seed) — C22 idempotent demo seed.

The real config lives in the app-db-config card (T2; not on the board yet), so
config attrs are injected by tests/conftest.py (see that file) as in 650.3.
"""
from decimal import Decimal

import pytest

from app.database import get_session_cm


@pytest.fixture()
def db():
    """A fresh seeded session: an empty schema per test (conftest autouse
    drops/init's before each test), wrapped so the seed uses the real helper."""
    with get_session_cm() as session:
        yield session


def _counts(session):
    from app.models.user import User
    from app.models.customer import Customer
    from app.models.supplier import Supplier
    from app.models.item import Item
    from app.models.order import Order, OrderLine
    from app.models.finance import Invoice, Payment
    from app.models.purchase import PurchaseOrder
    from app.models.tracking import DeliveryTrack, TrackingEvent

    return {
        "users": session.query(User).count(),
        "customers": session.query(Customer).count(),
        "suppliers": session.query(Supplier).count(),
        "items": session.query(Item).count(),
        "orders": session.query(Order).count(),
        "order_lines": session.query(OrderLine).count(),
        "invoices": session.query(Invoice).count(),
        "payments": session.query(Payment).count(),
        "pos": session.query(PurchaseOrder).count(),
        "tracks": session.query(DeliveryTrack).count(),
        "events": session.query(TrackingEvent).count(),
    }


def test_seed_populates_all_domain_tables(db):
    """A first boot seeds everything the demo needs: users, a customer, a
    supplier, a few items, and a complete order flow (order->invoice->payment
    + delivery track with events) plus a purchase order."""
    from app.seed import seed_if_empty

    seed_if_empty(db)

    c = _counts(db)
    # At least one user per role is expected — 5 users total.
    assert c["users"] >= 5, c
    assert c["customers"] >= 1, c
    assert c["suppliers"] >= 1, c
    assert c["items"] >= 3, c
    # One complete demo order flow.
    assert c["orders"] >= 1, c
    assert c["order_lines"] >= 1, c
    assert c["invoices"] >= 1, c
    assert c["payments"] >= 1, c
    assert c["tracks"] >= 1, c
    assert c["events"] >= 1, c
    assert c["pos"] >= 1, c


def test_seed_creates_admin_and_every_role(db):
    from app.models.user import User, ROLES

    from app.seed import seed_if_empty

    seed_if_empty(db)

    roles_seeded = {u.role for u in db.query(User).all()}
    # The closed role set is fully represented.
    assert set(ROLES) <= roles_seeded, roles_seeded
    # Exact usernames present.
    usernames = {u.username for u in db.query(User).all()}
    for expected in ("admin", "sales", "finance", "procurement", "customer"):
        assert expected in usernames, f"missing {expected} in {usernames}"


def test_seeded_passwords_are_hashed_and_verify(db):
    from app.auth import check_password
    from app.models.user import User

    from app.seed import seed_if_empty

    seed_if_empty(db)

    for u in db.query(User).all():
        # Never plaintext.
        assert u.password_hash != u.username
        # Demo passwords are documented demo-only credentials; each must be
        # checkable (no role is given a blank/empty password).
        assert u.password_hash.startswith("$2b$"), u.username
        assert check_password(_demo_password(u), u.password_hash), u.username


def _demo_password(user_row):
    from app.seed import DEMO_PASSWORDS

    return DEMO_PASSWORDS[user_row.role]


def test_demo_order_flow_is_consistent(db):
    """The seeded happy path order->invoice->payment must be internally
    consistent: invoice total matches its lines, payment matches total, and
    the delivery track carries the full event timeline."""
    from app.models.finance import Invoice
    from app.models.order import Order
    from app.models.tracking import DeliveryTrack

    from app.seed import seed_if_empty

    seed_if_empty(db)

    inv = db.query(Invoice).first()
    assert inv is not None
    # total == sum of line_totals.
    assert inv.total == sum((_l.line_total for _l in inv.lines), Decimal("0.00")), inv.total
    # Payment clears the invoice.
    assert sum((_p.amount for _p in inv.payments), Decimal("0.00")) == inv.total
    # One track per order, with the bound event timeline in order.
    track = db.query(DeliveryTrack).first()
    assert track is not None
    statuses = [e.status for e in track.events]
    from app.models.tracking import TRACK_EVENT

    assert statuses == list(TRACK_EVENT), statuses
    # order status reaches the demo happy-path terminal state.
    order = db.query(Order).first()
    assert order.status in ("confirmed", "shipped", "delivered")


def test_seed_is_idempotent(db):
    """Running seed twice adds nothing — users table non-empty short-circuits."""
    from app.models.item import Item
    from app.models.order import Order
    from app.models.user import User

    from app.seed import seed_if_empty

    seed_if_empty(db)
    users_after_first = db.query(User).count()
    totals_first = (db.query(Order).count(), db.query(Item).count())

    seed_if_empty(db)

    assert db.query(User).count() == users_after_first
    totals_second = (db.query(Order).count(), db.query(Item).count())
    assert totals_first == totals_second
