"""Tests for MC 650.9 (invoicing — fakturor).

Contract C16 (invoicing surface):
  POST   /api/orders/{id}/invoice  (roles [admin, finance]) -> InvoiceOut
         # 404 if order not confirmed; 409 if invoice exists; copies order lines
         # as invoice lines, total = sum(line_total) (all Decimals), status="issued"
  GET    /api/invoices             -> list[InvoiceOut]      ; [admin, finance]
  GET    /api/invoices/{id}        -> InvoiceOut (with lines + payments)
  PATCH  /api/invoices/{id}/status {status} -> InvoiceOut   ; draft->issued->paid

Roles: admin and finance only. The sales/customer/procurement roles never create
or mutate invoices; finance may read. All money is Decimal (I3), never float.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import app.config as _cfg

_cfg.SECRET_KEY = "test-secret-not-for-prod-0123456789abcdef"
_cfg.JWT_ALGORITHM = "HS256"
_cfg.ACCESS_TOKEN_EXPIRE_MINUTES = 60

from app.database import get_engine  # noqa: E402
from app.auth import create_access_token  # noqa: E402
from app.main import create_app  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def seed_base():
    """Persist one customer + two items; return ids and prices."""
    from app.models import Customer, Item

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
        s.commit()
    return ids


def _auth(client, role):
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _make_confirmed_order(client, seed_base, lines=None):
    """Create + confirm an order via the API; return its id."""
    if lines is None:
        lines = [
            {"item_id": seed_base["laptop"], "qty": 2},
            {"item_id": seed_base["monitor"], "qty": 3},
        ]
    body = {"customer_id": seed_base["customer_id"], "lines": lines}
    created = client.post("/api/orders", headers=_auth(client, "sales"), json=body)
    assert created.status_code == 200, created.text
    oid = created.json()["id"]
    r = client.post(f"/api/orders/{oid}/confirm", headers=_auth(client, "sales"))
    assert r.status_code == 200, r.text
    return oid


# ---------------------------------------------------------------------------
# Auth / role gating
# ---------------------------------------------------------------------------

def test_invoice_requires_auth(client):
    assert client.post("/api/orders/1/invoice").status_code == 401


def test_invoice_sales_forbidden(client, seed_base):
    oid = _make_confirmed_order(client, seed_base)
    assert client.post(
        f"/api/orders/{oid}/invoice", headers=_auth(client, "sales")
    ).status_code == 403
    assert client.get("/api/invoices", headers=_auth(client, "sales")).status_code == 403


# ---------------------------------------------------------------------------
# Create invoice from confirmed order
# ---------------------------------------------------------------------------

def test_invoice_from_confirmed_order(client, seed_base):
    oid = _make_confirmed_order(client, seed_base)
    r = client.post(f"/api/orders/{oid}/invoice", headers=_auth(client, "finance"))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["order_id"] == oid
    assert data["status"] == "issued"
    # total = 2x1000 + 3x250 = 2750.00, all Decimal.
    assert Decimal(data["total"]) == Decimal("2750.00")
    assert len(data["lines"]) == 2
    by_item = {ln["item_id"]: ln for ln in data["lines"]}
    assert Decimal(by_item[seed_base["laptop"]]["line_total"]) == Decimal("2000.00")
    assert Decimal(by_item[seed_base["monitor"]]["line_total"]) == Decimal("750.00")
    assert data["invoice_no"].startswith("INV-")
    assert data["paid_at"] is None


def test_invoice_not_confirmed_order_404(client, seed_base):
    body = {"customer_id": seed_base["customer_id"],
            "lines": [{"item_id": seed_base["laptop"], "qty": 1}]}
    created = client.post("/api/orders", headers=_auth(client, "sales"), json=body)
    oid = created.json()["id"]  # still draft
    r = client.post(f"/api/orders/{oid}/invoice", headers=_auth(client, "finance"))
    assert r.status_code == 404


def test_invoice_unknown_order_404(client):
    assert client.post("/api/orders/99999/invoice",
                       headers=_auth(client, "finance")).status_code == 404


def test_invoice_once_only_409(client, seed_base):
    oid = _make_confirmed_order(client, seed_base)
    assert client.post(f"/api/orders/{oid}/invoice",
                       headers=_auth(client, "finance")).status_code == 200
    assert client.post(f"/api/orders/{oid}/invoice",
                       headers=_auth(client, "finance")).status_code == 409


# ---------------------------------------------------------------------------
# List + get
# ---------------------------------------------------------------------------

def test_list_and_get_invoice(client, seed_base):
    oid = _make_confirmed_order(client, seed_base)
    inv = client.post(f"/api/orders/{oid}/invoice",
                      headers=_auth(client, "finance")).json()
    iid = inv["id"]

    lst = client.get("/api/invoices", headers=_auth(client, "finance"))
    assert lst.status_code == 200
    assert any(i["id"] == iid for i in lst.json())

    one = client.get(f"/api/invoices/{iid}", headers=_auth(client, "finance"))
    assert one.status_code == 200
    assert len(one.json()["lines"]) == 2


# ---------------------------------------------------------------------------
# Status patch (draft -> issued -> paid)
# ---------------------------------------------------------------------------

def test_status_patch_transitions(client, seed_base):
    oid = _make_confirmed_order(client, seed_base)
    iid = client.post(f"/api/orders/{oid}/invoice",
                      headers=_auth(client, "finance")).json()["id"]
    # issued -> issued (same) is a no-op allowed; keep to valid forward steps.
    assert client.patch(
        f"/api/invoices/{iid}/status", json={"status": "issued"},
        headers=_auth(client, "finance")).status_code == 200
    # paid is a forward transition from issued; allowed.
    r = client.patch(
        f"/api/invoices/{iid}/status", json={"status": "paid"},
        headers=_auth(client, "finance"))
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


def test_status_patch_invalid_value_422(client, seed_base):
    oid = _make_confirmed_order(client, seed_base)
    iid = client.post(f"/api/orders/{oid}/invoice",
                      headers=_auth(client, "finance")).json()["id"]
    r = client.patch(
        f"/api/invoices/{iid}/status", json={"status": "bogus"},
        headers=_auth(client, "finance"))
    assert r.status_code == 422


def test_status_patch_unknown_invoice_404(client):
    r = client.patch("/api/invoices/99999/status", json={"status": "issued"},
                     headers=_auth(client, "finance"))
    assert r.status_code == 404
