"""Tests for MC 650.11 (tracking - publik spårning / public tracking).

Contract C20 rev-3 / C21 rev-2:
  * A delivery track is looked up ONLY by the generated, non-sequential,
    high-entropy ``tracking_id`` (I5) - never by order id and never by the
    staff-only ``tracking_ref``.
  * This is a PUBLIC surface: it works with NO authentication, because the
    whole point is that the customer can follow their delivery without
    logging in.
  * Staff-internal fields never reach the wire: ``TrackingEvent.note`` is
    off-limits on the public surface, and the internal order id / tracking_ref
    are not disclosed.
  * An unknown or forged ``tracking_id`` returns 404 and must not reveal
    whether a track exists.

Surface (this card):
  GET /api/tracking/{tracking_id}    DeliveryTrackOut   (public, no auth)
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.config as _cfg

_cfg.SECRET_KEY = "test-secret-not-for-prod-0123456789abcdef"
_cfg.JWT_ALGORITHM = "HS256"
_cfg.ACCESS_TOKEN_EXPIRE_MINUTES = 60

from app.database import get_session  # noqa: E402
from app.models import Customer, DeliveryTrack, Item, Order, TRACK_EVENT, TrackingEvent  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def track_ids():
    """Persist a customer + order + delivery track with a full event
    timeline; return the public tracking_id and the internal order id."""
    from sqlalchemy.orm import Session
    from app.database import get_engine
    from secrets import token_hex

    ids = {}
    with Session(get_engine()) as s:
        cust = Customer(name="Spår Test AB", email="spar@t.example")
        s.add(cust)
        s.flush()
        order = Order(customer_id=cust.id, status="confirmed", tracking_ref="ORD-SECRET-9")
        s.add(order)
        s.flush()
        track = DeliveryTrack(order_id=order.id, carrier="postnord",
                              tracking_id=token_hex(16))
        s.add(track)
        s.flush()
        start = datetime.now(UTC) - timedelta(hours=40)
        for i, status in enumerate(TRACK_EVENT):
            s.add(TrackingEvent(
                delivery_track_id=track.id,
                status=status,
                note=f"INTERNT-{status}",   # staff-only, must never appear
                at=start + timedelta(hours=i * 8),
            ))
        ids["tracking_id"] = track.tracking_id
        ids["order_id"] = order.id
        s.commit()
    return ids


def _fresh_tracking_id():
    """Return a tracking_id shape that is NOT in the DB (forged)."""
    from secrets import token_hex
    return token_hex(16)


# ---------------------------------------------------------------------------
# The surface is PUBLIC - no auth token required
# ---------------------------------------------------------------------------

def test_public_tracking_needs_no_auth(client, track_ids):
    """The whole point of publik spårning: a bare GET with no Authorization
    header and no login must resolve the track via its tracking_id."""
    r = client.get(f"/api/tracking/{track_ids['tracking_id']}")
    assert r.status_code == 200, r.text


def test_tracking_is_keyed_by_tracking_id_not_order_id(client, track_ids):
    """The non-sequential tracking_id is the ONLY public key. The internal
    order id (an incrementing integer) resolves to 404 - it never leaks."""
    r = client.get(f"/api/tracking/{track_ids['order_id']}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Response shape + chronological timeline
# ---------------------------------------------------------------------------

def test_tracking_returns_carrier_and_event_timeline(client, track_ids):
    r = client.get(f"/api/tracking/{track_ids['tracking_id']}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tracking_id"] == track_ids["tracking_id"]
    assert data["carrier"] == "postnord"
    assert data["status"] == TRACK_EVENT[-1]          # latest = delivered
    assert len(data["events"]) == len(TRACK_EVENT)

    # Every event carries status + at timestamp, chronologically ordered.
    times = [e["at"] for e in data["events"]]
    assert times == sorted(times)
    assert [e["status"] for e in data["events"]] == list(TRACK_EVENT)


# ---------------------------------------------------------------------------
# Sanitisation: staff notes and internal ids never reach the public wire
# ---------------------------------------------------------------------------

def test_public_tracking_never_leaks_staff_note(client, track_ids):
    r = client.get(f"/api/tracking/{track_ids['tracking_id']}")
    body = r.text
    assert r.status_code == 200
    # Strong negative contract (C21 rev-2): the staff note text must not appear.
    assert "INTERNT-" not in body
    assert "note" not in r.json()["events"][0]
    # ... nor the internal labels.
    assert "tracking_ref" not in body
    assert "ORD-SECRET-9" not in body


def test_public_tracking_does_not_expose_internal_order_id(client, track_ids):
    r = client.get(f"/api/tracking/{track_ids['tracking_id']}")
    assert r.status_code == 200
    data = r.json()
    # The internal order id / tracking_ref are NOT fields of the public schema,
    # and the customer_id/order id never appear as values either.
    for key in ("order_id", "id", "tracking_ref", "customer_id"):
        assert key not in data
    assert data["tracking_id"] == track_ids["tracking_id"]


# ---------------------------------------------------------------------------
# Unknown / forged tracking id
# ---------------------------------------------------------------------------

def test_unknown_tracking_id_404(client):
    assert client.get(f"/api/tracking/{_fresh_tracking_id()}").status_code == 404
