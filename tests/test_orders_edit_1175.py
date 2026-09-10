"""Tests for MC 1175.1 — draft orders are editable (lines/qty) + cancel.

Surface added by this card:
  PATCH /api/orders/{id}           {lines:[{item_id,qty}]} -> OrderOut [admin,sales]
  PATCH /api/orders/{id}/status    {status:"cancel"}       -> OrderOut [admin,sales]

Rules under test:
  * Replace-lines re-snapshots prices server-side (C14): no price on the wire,
    and total follows the current Item prices, never the client.
  * Only a DRAFT is editable/cancellable: confirmed -> 409, cancelled -> 410,
    unknown id -> 404, unknown item id -> 404 with the draft left untouched.
  * Cancel is terminal and never touches stock (a draft never decremented).
  * Price-smuggling ({unit_price} / extra keys) -> 422 (extra="forbid").
  * finance (read+confirm role) may NOT edit -> 403.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import app.config as _cfg

_cfg.SECRET_KEY = "test-secret-not-for-prod-0123456789abcdef"
_cfg.JWT_ALGORITHM = "HS256"
_cfg.ACCESS_TOKEN_EXPIRE_MINUTES = 60

from app.database import get_session  # noqa: E402
from app.auth import create_access_token  # noqa: E402
from app.models import Customer, Item, Order  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def seed_base():
    """One customer + two items (stock 5 / 10) with known prices."""
    from sqlalchemy.orm import Session
    from app.database import get_engine

    ids = {}
    with Session(get_engine()) as s:
        cust = Customer(name="Test Kund AB", email="k@t.example")
        s.add(cust)
        s.flush()
        ids["customer_id"] = cust.id

        lap = Item(sku="IT-1175-LAP", name="Test Laptop",
                   unit_price=Decimal("1000.00"), qty_on_hand=5, active=True)
        mon = Item(sku="IT-1175-MON", name="Test Monitor",
                   unit_price=Decimal("2500.00"), qty_on_hand=10, active=True)
        s.add_all([lap, mon])
        s.commit()
        ids["laptop"], ids["laptop_price"] = lap.id, Decimal("1000.00")
        ids["monitor"], ids["monitor_price"] = mon.id, Decimal("2500.00")
        ids["stock_laptop"] = lap.qty_on_hand
    return ids


def _auth(client, role):
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _mk_draft(client, seed_base, qty=1):
    body = {
        "customer_id": seed_base["customer_id"],
        "lines": [{"item_id": seed_base["laptop"], "qty": qty}],
    }
    return client.post("/api/orders", headers=_auth(client, "sales"), json=body).json()


# --------------------------------------------------------------------------
# PATCH /api/orders/{id} — replace lines on a draft
# --------------------------------------------------------------------------

def test_patch_changes_qty_and_total(client, seed_base):
    oid = _mk_draft(client, seed_base)["id"]
    resp = client.patch(f"/api/orders/{oid}", headers=_auth(client, "sales"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 3}]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == "3000.00"
    assert len(body["lines"]) == 1 and body["lines"][0]["qty"] == 3


def test_patch_replaces_line_set(client, seed_base):
    """Replace = remove/add/change qty in ONE call; old lines are gone."""
    oid = _mk_draft(client, seed_base)["id"]
    resp = client.patch(f"/api/orders/{oid}", headers=_auth(client, "sales"), json={"lines": [
        {"item_id": seed_base["laptop"], "qty": 2},
        {"item_id": seed_base["monitor"], "qty": 1},
    ]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {ln["item_id"] for ln in body["lines"]} == {seed_base["laptop"], seed_base["monitor"]}
    assert body["total"] == "4500.00"
    # persisted, not just echoed
    assert client.get(f"/api/orders/{oid}", headers=_auth(client, "sales")).json() == body


def test_patch_resnapshots_current_prices(client, seed_base):
    """C14 through the edit path: an item price change is reflected server-side."""
    from sqlalchemy.orm import Session
    from app.database import get_engine

    oid = _mk_draft(client, seed_base)["id"]
    with Session(get_engine()) as s:  # price rises after the draft was made
        it = s.get(Item, seed_base["laptop"])
        it.unit_price = Decimal("1200.00")
        s.commit()
    resp = client.patch(f"/api/orders/{oid}", headers=_auth(client, "sales"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 1}]})
    assert resp.json()["lines"][0]["unit_price"] == "1200.00"
    assert resp.json()["total"] == "1200.00"


def test_patch_rejects_client_price(client, seed_base):
    """extra=forbid: unit_price on the wire is a 422, never a stored value."""
    oid = _mk_draft(client, seed_base)["id"]
    resp = client.patch(f"/api/orders/{oid}", headers=_auth(client, "sales"), json={"lines": [
        {"item_id": seed_base["laptop"], "qty": 1, "unit_price": "1.00"}]})
    assert resp.status_code == 422


def test_patch_rejects_zero_qty_and_empty_lines(client, seed_base):
    oid = _mk_draft(client, seed_base)["id"]
    h = _auth(client, "sales")
    assert client.patch(f"/api/orders/{oid}", headers=h,
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 0}]}).status_code == 422
    assert client.patch(f"/api/orders/{oid}", headers=h,
                        json={"lines": []}).status_code == 422


def test_patch_confirmed_order_409(client, seed_base):
    oid = _mk_draft(client, seed_base)["id"]
    assert client.post(f"/api/orders/{oid}/confirm",
                       headers=_auth(client, "sales")).status_code == 200
    resp = client.patch(f"/api/orders/{oid}", headers=_auth(client, "sales"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 9}]})
    assert resp.status_code == 409


def test_patch_unknown_order_404(client, seed_base):
    resp = client.patch("/api/orders/99999", headers=_auth(client, "sales"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 1}]})
    assert resp.status_code == 404


def test_patch_unknown_item_404_leaves_draft_untouched(client, seed_base):
    before = _mk_draft(client, seed_base, qty=2)
    resp = client.patch(f"/api/orders/{before['id']}", headers=_auth(client, "sales"),
                        json={"lines": [{"item_id": 99999, "qty": 1}]})
    assert resp.status_code == 404
    after = client.get(f"/api/orders/{before['id']}",
                       headers=_auth(client, "sales")).json()
    assert after["lines"] == before["lines"]  # atomic: nothing was replaced


def test_patch_finance_forbidden(client, seed_base):
    oid = _mk_draft(client, seed_base)["id"]
    resp = client.patch(f"/api/orders/{oid}", headers=_auth(client, "finance"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 3}]})
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# PATCH /api/orders/{id}/status — cancel
# --------------------------------------------------------------------------

def test_cancel_draft(client, seed_base):
    oid = _mk_draft(client, seed_base)["id"]
    resp = client.patch(f"/api/orders/{oid}/status", headers=_auth(client, "sales"),
                        json={"status": "cancel"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


def test_cancel_never_touches_stock(client, seed_base):
    """A draft never decremented, so cancelling must not restock either (I2)."""
    oid = _mk_draft(client, seed_base, qty=3)["id"]
    client.patch(f"/api/orders/{oid}/status", headers=_auth(client, "sales"),
                 json={"status": "cancel"})
    from sqlalchemy.orm import Session
    from app.database import get_engine
    with Session(get_engine()) as s:
        assert s.get(Item, seed_base["laptop"]).qty_on_hand == seed_base["stock_laptop"]


def test_cancel_confirmed_409(client, seed_base):
    oid = _mk_draft(client, seed_base)["id"]
    client.post(f"/api/orders/{oid}/confirm", headers=_auth(client, "sales"))
    resp = client.patch(f"/api/orders/{oid}/status", headers=_auth(client, "sales"),
                        json={"status": "cancel"})
    assert resp.status_code == 409


def test_cancel_is_terminal(client, seed_base):
    """Cancelled: re-cancel 409, edit 410, confirm 409 — no way back."""
    oid = _mk_draft(client, seed_base)["id"]
    h = _auth(client, "sales")
    client.patch(f"/api/orders/{oid}/status", headers=h, json={"status": "cancel"})
    assert client.patch(f"/api/orders/{oid}/status", headers=h,
                        json={"status": "cancel"}).status_code == 409
    assert client.patch(f"/api/orders/{oid}", headers=h,
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 1}]}).status_code == 410
    assert client.post(f"/api/orders/{oid}/confirm", headers=h).status_code == 409


def test_cancel_unknown_order_404(client, seed_base):
    resp = client.patch("/api/orders/99999/status", headers=_auth(client, "sales"),
                        json={"status": "cancel"})
    assert resp.status_code == 404


def test_status_patch_rejects_unknown_value(client, seed_base):
    """Closed transition set: anything but 'cancel' is a 422, nothing changes."""
    oid = _mk_draft(client, seed_base)["id"]
    resp = client.patch(f"/api/orders/{oid}/status", headers=_auth(client, "sales"),
                        json={"status": "confirmed"})
    assert resp.status_code == 422
    assert client.get(f"/api/orders/{oid}",
                      headers=_auth(client, "sales")).json()["status"] == "draft"
