"""Tests for MC 650.8 (sales-orders — orders).

Contract C13 rev-2 / C14:
  * Order + OrderLine; unit_price is a server-side SNAPSHOT of Item.unit_price
    taken at order creation — the wire carries only {item_id, qty}.
  * OrderLine.subtotal is computed server-side as qty * snapshotted unit_price
    (never client-supplied).
  * interest is coordinated via the stock single-owner adjust_stock (I2/C8)
    on order confirmation (stock-out).

Surface (this card):
  POST /api/orders                          OrderIn -> OrderOut   [admin, sales, finance]
  GET  /api/orders                          list[OrderOut]
  GET  /api/orders/{order_id}               OrderOut
  POST /api/orders/{order_id}/confirm       OrderOut            [admin, sales, finance]

Roles: staff who place/manage orders are admin, sales, finance. The customer
role never touches the internal sales surface here (customer order placement is
a later card); finance may read.
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
    """Persist one customer + two items directly, return their ids and prices."""
    from sqlalchemy.orm import Session
    from app.database import get_engine

    ids = {}
    with Session(get_engine()) as s:
        cust = Customer(name="Test Kund AB", email="k@t.example")
        s.add(cust)
        s.flush()
        ids["customer_id"] = cust.id

        lap = Item(sku="IT-TEST-LAP", name="Test Laptop",
                   unit_price=Decimal("1000.00"), qty_on_hand=5, active=True)
        mon = Item(sku="IT-TEST-MON", name="Test Monitor",
                   unit_price=Decimal("250.00"), qty_on_hand=3, active=True)
        s.add_all([lap, mon])
        s.flush()
        ids["laptop"] = lap.id
        ids["monitor"] = mon.id
        ids["laptop_price"] = lap.unit_price
        ids["monitor_price"] = mon.unit_price
        ids["stock_laptop"] = lap.qty_on_hand
        s.commit()
    return ids


def _auth(client, role):
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _customer_id(client):
    from app.database import get_engine
    from sqlalchemy.orm import Session
    with Session(get_engine()) as s:
        c = s.query(Customer).first()
        return c.id


# ---------------------------------------------------------------------------
# Auth / role gating
# ---------------------------------------------------------------------------

def test_create_order_requires_auth(client):
    assert client.post("/api/orders", json={}).status_code == 401


def test_customer_role_forbidden_create(client, seed_base):
    r = client.post(
        "/api/orders",
        headers=_auth(client, "customer"),
        json={"customer_id": seed_base["customer_id"], "lines": []},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Create order
# ---------------------------------------------------------------------------

def test_create_order_snapshots_price_and_total(client, seed_base):
    body = {
        "customer_id": seed_base["customer_id"],
        "lines": [
            {"item_id": seed_base["laptop"], "qty": 2},
            {"item_id": seed_base["monitor"], "qty": 3},
        ],
    }
    r = client.post("/api/orders", headers=_auth(client, "sales"), json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "draft"
    assert len(data["lines"]) == 2
    by_item = {ln["item_id"]: ln for ln in data["lines"]}
    # unit_price is snapshotted server-side (not client), subtotal computed.
    assert Decimal(by_item[seed_base["laptop"]]["unit_price"]) == Decimal("1000.00")
    assert Decimal(by_item[seed_base["laptop"]]["subtotal"]) == Decimal("2000.00")
    assert Decimal(by_item[seed_base["monitor"]]["unit_price"]) == Decimal("250.00")
    assert Decimal(by_item[seed_base["monitor"]]["subtotal"]) == Decimal("750.00")
    # Total is the sum of line subtotals.
    assert Decimal(data["total"]) == Decimal("2750.00")
    # Stock NOT yet touched while draft.
    from app.services import catalog
    from sqlalchemy.orm import Session
    from app.database import get_engine
    with Session(get_engine()) as s:
        it = s.get(Item, seed_base["laptop"])
        assert it.qty_on_hand == seed_base["stock_laptop"]


def test_create_order_unknown_customer_404(client, seed_base):
    body = {"customer_id": 99999, "lines": [{"item_id": seed_base["laptop"], "qty": 1}]}
    r = client.post("/api/orders", headers=_auth(client, "sales"), json=body)
    assert r.status_code == 404


def test_create_order_unknown_item_404(client, seed_base):
    body = {"customer_id": seed_base["customer_id"], "lines": [{"item_id": 99999, "qty": 1}]}
    r = client.post("/api/orders", headers=_auth(client, "sales"), json=body)
    assert r.status_code == 404


def test_create_order_rejects_zero_quantity(client, seed_base):
    body = {
        "customer_id": seed_base["customer_id"],
        "lines": [{"item_id": seed_base["laptop"], "qty": 0}],
    }
    r = client.post("/api/orders", headers=_auth(client, "sales"), json=body)
    assert r.status_code == 422  # qty ge=1 via schema


def test_create_order_requires_lines(client, seed_base):
    body = {"customer_id": seed_base["customer_id"], "lines": []}
    r = client.post("/api/orders", headers=_auth(client, "sales"), json=body)
    assert r.status_code == 422  # min_length=1


# ---------------------------------------------------------------------------
# List + get
# ---------------------------------------------------------------------------

def test_list_and_get_order(client, seed_base):
    body = {
        "customer_id": seed_base["customer_id"],
        "lines": [{"item_id": seed_base["laptop"], "qty": 1}],
    }
    created = client.post("/api/orders", headers=_auth(client, "sales"), json=body).json()
    oid = created["id"]

    lst = client.get("/api/orders", headers=_auth(client, "finance"))
    assert lst.status_code == 200
    assert any(o["id"] == oid for o in lst.json())

    one = client.get(f"/api/orders/{oid}", headers=_auth(client, "sales"))
    assert one.status_code == 200
    assert one.json()["lines"][0]["item_id"] == seed_base["laptop"]


# ---------------------------------------------------------------------------
# Confirm (stock-out via catalog.adjust_stock)
# ---------------------------------------------------------------------------

def test_confirm_moves_status_and_removes_stock(client, seed_base):
    body = {
        "customer_id": seed_base["customer_id"],
        "lines": [{"item_id": seed_base["laptop"], "qty": 2}],
    }
    created = client.post("/api/orders", headers=_auth(client, "sales"), json=body).json()
    oid = created["id"]
    assert created["status"] == "draft"

    r = client.post(f"/api/orders/{oid}/confirm", headers=_auth(client, "sales"))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"

    from sqlalchemy.orm import Session
    from app.database import get_engine
    with Session(get_engine()) as s:
        it = s.get(Item, seed_base["laptop"])
        assert it.qty_on_hand == seed_base["stock_laptop"] - 2


def test_confirm_insufficient_stock_400(client, seed_base):
    body = {
        "customer_id": seed_base["customer_id"],
        "lines": [
            {"item_id": seed_base["laptop"], "qty": 100},  # only 5 on hand
        ],
    }
    created = client.post("/api/orders", headers=_auth(client, "sales"), json=body).json()
    oid = created["id"]
    r = client.post(f"/api/orders/{oid}/confirm", headers=_auth(client, "sales"))
    assert r.status_code in (400, 409)
    # No partial decrement: stock unchanged.
    from sqlalchemy.orm import Session
    from app.database import get_engine
    with Session(get_engine()) as s:
        it = s.get(Item, seed_base["laptop"])
        assert it.qty_on_hand == seed_base["stock_laptop"]


def test_confirm_unknown_order_404(client):
    assert client.post("/api/orders/99999/confirm",
                       headers=_auth(client, "sales")).status_code == 404


def test_confirm_once_only(client, seed_base):
    body = {
        "customer_id": seed_base["customer_id"],
        "lines": [{"item_id": seed_base["laptop"], "qty": 1}],
    }
    created = client.post("/api/orders", headers=_auth(client, "sales"), json=body).json()
    oid = created["id"]
    assert client.post(f"/api/orders/{oid}/confirm",
                       headers=_auth(client, "sales")).status_code == 200
    # second confirm -> 409 (already confirmed) and no double stock-out
    assert client.post(f"/api/orders/{oid}/confirm",
                       headers=_auth(client, "sales")).status_code == 409
