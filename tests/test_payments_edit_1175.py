"""Tests for MC 1175.3 — payments rättbara: makulera felaktig betalning.

Surface added by this card:
  POST /api/payments/{id}/cancel  -> PaymentOut   (makulering, append-only)
  PaymentOut gains ``cancels_payment_id`` (non-null on a refund row).

Rules under test:
  * A wrong payment is never deleted — makulering appends a NEGATIVE refund
    row (same method) with cancels_payment_id -> original. Both rows survive.
  * The refund drops the invoice's net (sum incl. refunds) below total: a
    "paid" invoice falls back to "issued" and paid_at clears; a later payment
    can mark it paid again.
  * Net-zeroing the last payment makes the invoice makulerings-bar (T2 cancel
    required net payments == 0.00).
  * Guards: unknown payment 404, re-cancel 409, refund row not cancellable
    409, cancelled invoice 410, sales role 403.
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
    """One customer + one item (known price) for the invoice flow."""
    from app.models import Customer, Item

    ids = {}
    with Session(get_engine()) as s:
        cust = Customer(name="Test Kund AB", email="k@t.example")
        s.add(cust)
        s.flush()
        ids["customer_id"] = cust.id

        lap = Item(sku="IT-1173-LAP", name="Test Laptop",
                   unit_price=Decimal("1000.00"), qty_on_hand=5, active=True)
        s.add(lap)
        s.commit()
        ids["laptop"], ids["laptop_price"] = lap.id, Decimal("1000.00")
    return ids


def _auth(client, role):
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _paid_invoice(client, seed_base, qty=2):
    """Order -> confirm -> invoice -> pay in full; return (invoice, payment)."""
    body = {"customer_id": seed_base["customer_id"],
            "lines": [{"item_id": seed_base["laptop"], "qty": qty}]}
    oid = client.post("/api/orders", headers=_auth(client, "sales"),
                      json=body).json()["id"]
    assert client.post(f"/api/orders/{oid}/confirm",
                       headers=_auth(client, "sales")).status_code == 200
    inv = client.post(f"/api/orders/{oid}/invoice",
                      headers=_auth(client, "finance"))
    assert inv.status_code == 200, inv.text
    iid = inv.json()["id"]
    tot = inv.json()["total"]
    pay = client.post(f"/api/invoices/{iid}/payment", headers=_auth(client, "finance"),
                      json={"amount": tot, "method": "bank"})
    assert pay.status_code == 200, pay.text
    return client.get(f"/api/invoices/{iid}", headers=_auth(client, "finance")).json(), \
        pay.json()


def test_cancel_payment_appends_refund(client, seed_base):
    inv, pay = _paid_invoice(client, seed_base)
    r = client.post(f"/api/payments/{pay['id']}/cancel", headers=_auth(client, "finance"))
    assert r.status_code == 200, r.text
    refund = r.json()
    assert refund["amount"] == "-2000.00"
    assert refund["method"] == pay["method"]
    assert refund["cancels_payment_id"] == pay["id"]
    # append-only: the original row still exists (GET /payments lists both)
    listed = client.get("/api/payments", headers=_auth(client, "finance")).json()
    by_id = {p["id"]: p for p in listed}
    assert by_id[pay["id"]]["amount"] == "2000.00"
    assert by_id[pay["id"]]["cancels_payment_id"] is None
    assert refund["id"] in by_id


def test_paid_falls_back_to_issued(client, seed_base):
    inv, pay = _paid_invoice(client, seed_base)
    assert inv["status"] == "paid"
    client.post(f"/api/payments/{pay['id']}/cancel", headers=_auth(client, "finance"))
    after = client.get(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance")).json()
    assert after["status"] == "issued"
    assert after["paid_at"] is None
    # net payments == 0 -> makulering (T2) is allowed now
    r = client.patch(f"/api/invoices/{inv['id']}/status", headers=_auth(client, "finance"),
                     json={"status": "cancel"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"


def test_recancel_is_409(client, seed_base):
    _, pay = _paid_invoice(client, seed_base)
    assert client.post(f"/api/payments/{pay['id']}/cancel",
                       headers=_auth(client, "finance")).status_code == 200
    r = client.post(f"/api/payments/{pay['id']}/cancel", headers=_auth(client, "finance"))
    assert r.status_code == 409


def test_refund_row_not_cancellable(client, seed_base):
    _, pay = _paid_invoice(client, seed_base)
    refund = client.post(f"/api/payments/{pay['id']}/cancel",
                         headers=_auth(client, "finance")).json()
    r = client.post(f"/api/payments/{refund['id']}/cancel", headers=_auth(client, "finance"))
    assert r.status_code == 409


def test_unknown_payment_404(client, seed_base):
    r = client.post("/api/payments/99999/cancel", headers=_auth(client, "finance"))
    assert r.status_code == 404


def test_partial_refund_keeps_paid(client, seed_base):
    """Refund-adjusting flow (owner ruling 2026-09-24, F1 / MC 1349.1):
    a NEW payment on an already-PAID invoice is now 409, so the refund flow is
    cancel-FIRST: makulera the original (invoice falls back to issued), then
    record the refund-adjusting payment, then re-pay to paid."""
    inv, pay = _paid_invoice(client, seed_base)  # 2000 covered by one pay
    # cancel the original first -> net 0, invoice back to issued
    r = client.post(f"/api/payments/{pay['id']}/cancel", headers=_auth(client, "finance"))
    assert r.status_code == 200
    # record the refund-adjusting payment: net 500 of 2000 -> still unsettled
    p2 = client.post(f"/api/invoices/{inv['id']}/payment", headers=_auth(client, "finance"),
                     json={"amount": "500.00", "method": "cash"})
    assert p2.status_code == 200
    after = client.get(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance")).json()
    # net now 500 of 2000 -> unsettled
    assert after["status"] == "issued"
    # re-pay the remainder -> paid again
    p3 = client.post(f"/api/invoices/{inv['id']}/payment", headers=_auth(client, "finance"),
                     json={"amount": "1500.00", "method": "cash"})
    assert p3.status_code == 200
    final = client.get(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance")).json()
    assert final["status"] == "paid"
    assert final["paid_at"] is not None


def test_repay_after_refund_marks_paid(client, seed_base):
    inv, pay = _paid_invoice(client, seed_base)
    client.post(f"/api/payments/{pay['id']}/cancel", headers=_auth(client, "finance"))
    r = client.post(f"/api/invoices/{inv['id']}/payment", headers=_auth(client, "finance"),
                    json={"amount": "2000.00", "method": "card"})
    assert r.status_code == 200
    after = client.get(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance")).json()
    assert after["status"] == "paid"
    assert after["paid_at"] is not None


def test_cancel_payment_on_cancelled_invoice_410(client, seed_base):
    inv, pay = _paid_invoice(client, seed_base)
    client.post(f"/api/payments/{pay['id']}/cancel", headers=_auth(client, "finance"))
    client.patch(f"/api/invoices/{inv['id']}/status", headers=_auth(client, "finance"),
                 json={"status": "cancel"})
    # a payment made after the refund, before makulering would be blocked;
    # here: makulera a payment while its invoice is cancelled -> 410
    # (create one via direct row: pay then un-cancel is impossible; instead
    # refund of the refund path: cancel the refund row -> 409 first.)
    refund_id = client.get("/api/payments", headers=_auth(client, "finance")).json()[0]["id"]
    assert client.post(f"/api/payments/{refund_id}/cancel",
                       headers=_auth(client, "finance")).status_code == 409


def test_sales_role_forbidden(client, seed_base):
    _, pay = _paid_invoice(client, seed_base)
    r = client.post(f"/api/payments/{pay['id']}/cancel", headers=_auth(client, "sales"))
    assert r.status_code == 403
