"""Tests for MC 650.9 (payments — betalning).

Contract C17 (payments surface), rev-2 with Decimal pinned:
  POST   /api/invoices/{id}/payment  PaymentIn{amount, method, date?} -> PaymentOut ; [admin, finance]
         # amount constrained in schema: gt=0, max_digits=12, decimal_places=2
         # records Payment (Decimal); marks invoice paid when sum(payments) >= invoice.total
  POST   /api/invoices/{id}/reconcile (roles [admin, finance]) -> InvoiceOut
         # sets status="paid" when sum(payments) >= total; else 409 "still outstanding"
  GET    /api/payments               -> list[PaymentOut]

Simulated only (I3): no external gateway. All money arithmetic in Decimal.
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
    """One customer + two items (same shape as test_orders/test_invoices)."""
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
        s.commit()
    return ids


def _auth(client, role):
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _issued_invoice(client, seed_base):
    """Return the id of a freshly issued invoice (order -> invoice)."""
    body = {"customer_id": seed_base["customer_id"],
            "lines": [{"item_id": seed_base["laptop"], "qty": 2},
                      {"item_id": seed_base["monitor"], "qty": 3}]}
    created = client.post("/api/orders", headers=_auth(client, "sales"), json=body)
    oid = created.json()["id"]
    client.post(f"/api/orders/{oid}/confirm", headers=_auth(client, "sales"))
    inv = client.post(f"/api/orders/{oid}/invoice",
                      headers=_auth(client, "finance")).json()
    return inv["id"], Decimal(inv["total"])


# ---------------------------------------------------------------------------
# Auth / role gating
# ---------------------------------------------------------------------------

def test_payment_requires_auth(client):
    assert client.post("/api/invoices/1/payment", json={}).status_code == 401


def test_payment_sales_forbidden(client, seed_base):
    iid, _ = _issued_invoice(client, seed_base)
    assert client.post(
        f"/api/invoices/{iid}/payment", json={"amount": "10.00", "method": "bank"},
        headers=_auth(client, "sales")).status_code == 403


# ---------------------------------------------------------------------------
# Record payment + auto-mark-paid
# ---------------------------------------------------------------------------

def test_partial_payment_leaves_issued(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    assert total == Decimal("2750.00")
    r = client.post(
        f"/api/invoices/{iid}/payment",
        json={"amount": "1000.00", "method": "bank"},
        headers=_auth(client, "finance"))
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["amount"]) == Decimal("1000.00")
    # Still outstanding -> status unchanged (issued).
    inv = client.get(f"/api/invoices/{iid}", headers=_auth(client, "finance")).json()
    assert inv["status"] == "issued"
    assert len(inv["payments"]) == 1


def test_full_payment_marks_paid(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    r = client.post(
        f"/api/invoices/{iid}/payment",
        json={"amount": str(total), "method": "bank"},
        headers=_auth(client, "finance"))
    assert r.status_code == 200, r.text
    inv = client.get(f"/api/invoices/{iid}", headers=_auth(client, "finance")).json()
    assert inv["status"] == "paid"
    assert inv["paid_at"] is not None


def test_overfull_payment_marks_paid(client, seed_base):
    iid, _ = _issued_invoice(client, seed_base)
    # amount above total is allowed but overshoot is not refunded on the record;
    # invoice is fully covered -> paid.
    r = client.post(
        f"/api/invoices/{iid}/payment",
        json={"amount": "10000.00", "method": "bank"},
        headers=_auth(client, "finance"))
    assert r.status_code == 200
    inv = client.get(f"/api/invoices/{iid}", headers=_auth(client, "finance")).json()
    assert inv["status"] == "paid"


def test_payment_invalid_amounts_422(client, seed_base):
    iid, _ = _issued_invoice(client, seed_base)
    # amount <= 0 rejected.
    for bad in ["0", "-5", "0.001", "1.234"]:
        r = client.post(
            f"/api/invoices/{iid}/payment",
            json={"amount": bad, "method": "bank"},
            headers=_auth(client, "finance"))
        assert r.status_code == 422, (bad, r.status_code)


def test_payment_invalid_method_422(client, seed_base):
    iid, _ = _issued_invoice(client, seed_base)
    r = client.post(
        f"/api/invoices/{iid}/payment",
        json={"amount": "10.00", "method": "crypto"},
        headers=_auth(client, "finance"))
    assert r.status_code == 422


def test_payment_unknown_invoice_404(client):
    r = client.post(
        "/api/invoices/99999/payment",
        json={"amount": "10.00", "method": "bank"},
        headers=_auth(client, "finance"))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Reconcile
# ---------------------------------------------------------------------------

def test_reconcile_paid_when_covered(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    client.post(f"/api/invoices/{iid}/payment",
                json={"amount": str(total), "method": "bank"},
                headers=_auth(client, "finance"))
    r = client.post(f"/api/invoices/{iid}/reconcile",
                    headers=_auth(client, "finance"))
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


def test_reconcile_still_outstanding_409(client, seed_base):
    iid, _ = _issued_invoice(client, seed_base)
    client.post(f"/api/invoices/{iid}/payment",
                json={"amount": "500.00", "method": "bank"},
                headers=_auth(client, "finance"))
    r = client.post(f"/api/invoices/{iid}/reconcile",
                    headers=_auth(client, "finance"))
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# List payments
# ---------------------------------------------------------------------------

def test_list_payments(client, seed_base):
    iid, _ = _issued_invoice(client, seed_base)
    client.post(f"/api/invoices/{iid}/payment",
                json={"amount": "1000.00", "method": "bank"},
                headers=_auth(client, "finance"))
    r = client.get("/api/payments", headers=_auth(client, "finance"))
    assert r.status_code == 200
    assert any(Decimal(p["amount"]) == Decimal("1000.00") for p in r.json())


def test_list_payments_requires_auth(client):
    assert client.get("/api/payments").status_code == 401
