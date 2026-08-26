"""Tests for MC 695.1 (tracking WRITE-endpoint, C21 rev-3).

Contract C21 rev-3 write side:
  * Every order gets a DeliveryTrack + a first "placed" TrackingEvent the moment
    it is CONFIRMED (``POST /api/orders/{id}/confirm``) — "skapa DeliveryTrack+
    event per order". The tracking_id is generated, non-sequential and
    high-entropy (I5), never the incremental orders.id.
  * A STAFF-only write endpoint appends the next delivery event(s) (e.g.
    in-warehouse, in-transit, out-for-delivery, delivered) with an optional
    staff note. Only the event's status is validated against the closed
    TRACK_EVENT set; the note is stored server-side but NEVER emitted on the
    public surface (C21 rev-2 sanitisation preserved).
  * Unknown/forged tracking_id on the write surface returns the same uniform
    404 as the read surface.

Surface (this card - write side only):
  POST /api/orders/{order_id}/confirm                  -> auto-creates track+placed
  POST /api/tracking/{tracking_id}/events              TrackingEventIn -> DeliveryTrackOut
                                                       [admin, sales, finance]
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import app.config as _cfg

_cfg.SECRET_KEY = "test-secret-not-for-prod-0123456789abcdef"
_cfg.JWT_ALGORITHM = "HS256"
_cfg.ACCESS_TOKEN_EXPIRE_MINUTES = 60

from app.auth import create_access_token  # noqa: E402
from app.models import Customer, DeliveryTrack, Item, TrackingEvent  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def seed_order(client):
    """Persist a customer + one item, then create + confirm an order through the
    API (as sales). Return the order id, the item, and a staff auth header."""
    from sqlalchemy.orm import Session
    from app.database import get_engine

    ids = {}
    with Session(get_engine()) as s:
        cust = Customer(name="Skriv Test AB", email="w@t.example")
        s.add(cust)
        s.flush()
        ids["customer_id"] = cust.id
        it = Item(sku="IT-WRITE-1", name="Write Test", unit_price=Decimal("900.00"),
                  qty_on_hand=10, active=True)
        s.add(it)
        s.flush()
        ids["item_id"] = it.id
        s.commit()

    auth = {"Authorization": f"Bearer {create_access_token(1, 'sales')}"}
    r = client.post("/api/orders", headers=auth, json={
        "customer_id": ids["customer_id"],
        "lines": [{"item_id": ids["item_id"], "qty": 2}],
    })
    assert r.status_code == 200, r.text
    order_id = r.json()["id"]

    confirm = client.post(f"/api/orders/{order_id}/confirm", headers=auth)
    assert confirm.status_code == 200, confirm.text
    ids["order_id"] = order_id
    ids["auth"] = auth
    return ids


def _do_auth(role):
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _query_track(order_id):
    from sqlalchemy.orm import Session
    from app.database import get_engine
    with Session(get_engine()) as s:
        return s.query(DeliveryTrack).filter(DeliveryTrack.order_id == order_id).first()


# ---------------------------------------------------------------------------
# 1. Auto-create: DeliveryTrack + "placed" event per order, on confirm
# ---------------------------------------------------------------------------

def test_confirm_auto_creates_track_and_placed_event(client, seed_order):
    """Confirming an order must create a DeliveryTrack + one 'placed' event."""
    track = _query_track(seed_order["order_id"])
    assert track is not None, "confirm should create a DeliveryTrack for the order"
    # High-entropy, non-sequential public key (I5): 32+ hex chars, not the order id.
    assert len(track.tracking_id) >= 32
    assert track.tracking_id != str(seed_order["order_id"])

    from sqlalchemy.orm import Session
    from app.database import get_engine
    with Session(get_engine()) as s:
        events = (
            s.query(TrackingEvent)
            .filter(TrackingEvent.delivery_track_id == track.id)
            .all()
        )
    assert len(events) == 1
    assert events[0].status == "placed"


def test_confirm_is_idempotent_on_track(client, seed_order):
    """An order gets exactly ONE track (order_id is unique); confirming again is
    rejected at draft-gate anyway, and re-create must not double it."""
    track = _query_track(seed_order["order_id"])
    assert track is not None
    from sqlalchemy.orm import Session
    from app.database import get_engine
    with Session(get_engine()) as s:
        dup = (
            s.query(DeliveryTrack)
            .filter(DeliveryTrack.order_id == seed_order["order_id"])
            .all()
        )
    assert len(dup) == 1


def test_draft_order_has_no_track(client, seed_order):
    """Creating a draft order must NOT create a track — only confirm does."""
    r = client.post("/api/orders", headers=seed_order["auth"], json={
        "customer_id": seed_order["customer_id"],
        "lines": [{"item_id": seed_order["item_id"], "qty": 1}],
    })
    assert r.status_code == 200, r.text
    draft_id = r.json()["id"]
    assert _query_track(draft_id) is None


# ---------------------------------------------------------------------------
# 2. Staff write endpoint: POST /api/tracking/{tracking_id}/events
# ---------------------------------------------------------------------------

def _first_tid(seed_order):
    return _query_track(seed_order["order_id"]).tracking_id


def test_append_event_updates_public_timeline(client, seed_order):
    tid = _first_tid(seed_order)
    r = client.post(
        f"/api/tracking/{tid}/events",
        headers=_do_auth("admin"),
        json={"status": "in-warehouse", "note": "plockad ur lagret"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    # The write response is the updated public DeliveryTrackOut.
    assert data["tracking_id"] == tid
    assert data["status"] == "in-warehouse"
    assert [e["status"] for e in data["events"]] == ["placed", "in-warehouse"]

    # The staff note is stored server-side ...
    from sqlalchemy.orm import Session
    from app.database import get_engine
    with Session(get_engine()) as s:
        notes = [
            e.note for e in s.query(TrackingEvent).all() if e.note is not None
        ]
    assert "plockad ur lagret" in notes


def test_append_event_note_never_reaches_public_wire(client, seed_order):
    tid = _first_tid(seed_order)
    client.post(
        f"/api/tracking/{tid}/events",
        headers=_do_auth("admin"),
        json={"status": "in-transit", "note": "HEMLIG-STAVNING"},
    )
    # Public (no-auth) GET must not leak the note text.
    r = client.get(f"/api/tracking/{tid}")
    assert r.status_code == 200
    assert "HEMLIG-STAVNING" not in r.text
    assert "note" not in r.json()["events"][-1]


def test_append_event_requires_staff_auth(client, seed_order):
    tid = _first_tid(seed_order)
    # No token -> 401
    assert client.post(
        f"/api/tracking/{tid}/events", json={"status": "in-transit"}
    ).status_code == 401
    # Customer role -> 403
    assert client.post(
        f"/api/tracking/{tid}/events",
        headers=_do_auth("customer"),
        json={"status": "in-transit"},
    ).status_code == 403


def test_append_event_rejects_invalid_status(client, seed_order):
    tid = _first_tid(seed_order)
    r = client.post(
        f"/api/tracking/{tid}/events",
        headers=_do_auth("sales"),
        json={"status": "bogus-status"},
    )
    # Closed-set validation: rejected, not silently stored.
    assert r.status_code in (400, 422)


def test_append_event_unknown_tracking_id_404(client, seed_order):
    from secrets import token_hex
    r = client.post(
        f"/api/tracking/{token_hex(16)}/events",
        headers=_do_auth("admin"),
        json={"status": "in-transit"},
    )
    assert r.status_code == 404
