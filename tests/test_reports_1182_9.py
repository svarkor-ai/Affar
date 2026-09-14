"""Tests for MC 1182.9 — reports/dashboard (monthly sales, AR-aging, stock).

Contract (new, MC 1182.9):
  GET /api/reports/monthly-sales?months=N -> list[MonthlySalesRow]  [admin, finance]
  GET /api/reports/ar-aging               -> ArAgingOut             [admin, finance]
  GET /api/reports/stock-balance          -> StockBalanceOut        [admin, procurement]

All three are pure reads. Cancelled invoices are excluded everywhere.
Money is Decimal 12,2 end to end (I3).
"""

from datetime import UTC, datetime, timedelta
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
from app.models import Invoice, Payment  # noqa: E402
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
    """Return (invoice_id, total) of a freshly issued invoice."""
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

def test_monthly_sales_requires_auth(client):
    assert client.get("/api/reports/monthly-sales").status_code == 401


def test_ar_aging_requires_auth(client):
    assert client.get("/api/reports/ar-aging").status_code == 401


def test_stock_balance_requires_auth(client):
    assert client.get("/api/reports/stock-balance").status_code == 401


def test_monthly_sales_sales_role_forbidden(client):
    # Sales/AR reports are finance+admin only.
    assert client.get("/api/reports/monthly-sales",
                      headers=_auth(client, "sales")).status_code == 403


def test_stock_balance_finance_forbidden(client):
    # Stock report is procurement+admin only.
    assert client.get("/api/reports/stock-balance",
                      headers=_auth(client, "finance")).status_code == 403


# ---------------------------------------------------------------------------
# Monthly sales
# ---------------------------------------------------------------------------

def test_monthly_sales_counts_issued_and_paid(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    r = client.get("/api/reports/monthly-sales", headers=_auth(client, "finance"))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 12  # default window, zero-filled
    this_month = rows[-1]
    assert this_month["month"] == datetime.now(UTC).strftime("%Y-%m")
    # The demo seed (seed_if_empty) also issues one paid invoice this month;
    # expected = seed total + this test's invoice total.
    with Session(get_engine()) as s:
        seed_total = sum(
            (Decimal(t) for (t,) in s.query(Invoice.total)
             .filter(Invoice.status.in_(("issued", "paid")))),
            Decimal("0.00"),
        ) - total
    assert Decimal(this_month["total"]) == seed_total + total


def test_monthly_sales_excludes_cancelled(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    # Cancel the invoice (makulering) — its contribution must vanish.
    r = client.patch(f"/api/invoices/{iid}/status",
                     json={"status": "cancel"}, headers=_auth(client, "finance"))
    assert r.status_code == 200, r.text
    rows = client.get("/api/reports/monthly-sales",
                      headers=_auth(client, "admin")).json()
    with Session(get_engine()) as s:
        seed_total = sum(
            (Decimal(t) for (t,) in s.query(Invoice.total)
             .filter(Invoice.status.in_(("issued", "paid")))),
            Decimal("0.00"),
        )
    assert Decimal(rows[-1]["total"]) == seed_total


def test_monthly_sales_months_param(client, seed_base):
    r = client.get("/api/reports/monthly-sales?months=3",
                   headers=_auth(client, "admin"))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3
    assert rows[-1]["month"] == datetime.now(UTC).strftime("%Y-%m")


# ---------------------------------------------------------------------------
# AR-aging
# ---------------------------------------------------------------------------

def test_ar_aging_buckets_issued_invoice(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    r = client.get("/api/reports/ar-aging", headers=_auth(client, "finance"))
    assert r.status_code == 200, r.text
    data = r.json()
    assert Decimal(data["buckets"]["0-30"]) == total
    assert Decimal(data["total_outstanding"]) == total
    assert len(data["invoices"]) == 1
    assert data["invoices"][0]["invoice_id"] == iid
    assert data["invoices"][0]["days_overdue"] <= 30


def test_ar_aging_paid_invoice_not_receivable(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    client.post(f"/api/invoices/{iid}/payment",
                json={"amount": str(total), "method": "bank"},
                headers=_auth(client, "finance"))
    data = client.get("/api/reports/ar-aging",
                      headers=_auth(client, "finance")).json()
    assert Decimal(data["total_outstanding"]) == 0
    assert data["invoices"] == []


def test_ar_aging_partial_payment_nets_out(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    client.post(f"/api/invoices/{iid}/payment",
                json={"amount": "1000.00", "method": "bank"},
                headers=_auth(client, "finance"))
    data = client.get("/api/reports/ar-aging",
                      headers=_auth(client, "finance")).json()
    assert Decimal(data["total_outstanding"]) == total - Decimal("1000.00")


def test_ar_aging_old_invoice_lands_in_90_plus(client, seed_base):
    iid, total = _issued_invoice(client, seed_base)
    # Backdate the issue date 100 days directly (service-level aging check).
    with Session(get_engine()) as s:
        inv = s.get(Invoice, iid)
        inv.issued_at = datetime.now(UTC) - timedelta(days=100)
        s.commit()
    data = client.get("/api/reports/ar-aging",
                      headers=_auth(client, "finance")).json()
    assert Decimal(data["buckets"]["90+"]) == total
    assert Decimal(data["buckets"]["0-30"]) == 0


def test_ar_aging_cancelled_excluded(client, seed_base):
    iid, _ = _issued_invoice(client, seed_base)
    client.patch(f"/api/invoices/{iid}/status",
                 json={"status": "cancel"}, headers=_auth(client, "finance"))
    data = client.get("/api/reports/ar-aging",
                      headers=_auth(client, "finance")).json()
    assert Decimal(data["total_outstanding"]) == 0
    assert data["invoices"] == []


# ---------------------------------------------------------------------------
# Stock balance
# ---------------------------------------------------------------------------

def test_stock_balance_rows_and_total(client, seed_base):
    r = client.get("/api/reports/stock-balance",
                   headers=_auth(client, "procurement"))
    assert r.status_code == 200, r.text
    data = r.json()
    by_sku = {row["sku"]: row for row in data["items"]}
    lap = by_sku["IT-TEST-LAP"]
    assert lap["qty_on_hand"] == 5
    assert Decimal(lap["stock_value"]) == Decimal("5000.00")
    mon = by_sku["IT-TEST-MON"]
    assert Decimal(mon["stock_value"]) == Decimal("750.00")
    # Total = every item's qty*price (the demo seed adds its own items).
    from app.models import Item as ItemModel

    with Session(get_engine()) as s:
        expected = sum(
            (Decimal(it.qty_on_hand) * Decimal(it.unit_price)
             for it in s.query(ItemModel)),
            Decimal("0.00"),
        )
    assert Decimal(data["total_value"]) == expected


def test_stock_balance_includes_inactive_flagged(client, seed_base):
    from app.models import Item as ItemModel

    with Session(get_engine()) as s:
        for item in s.query(ItemModel):
            item.active = False
        s.commit()
    data = client.get("/api/reports/stock-balance",
                      headers=_auth(client, "procurement")).json()
    assert data["items"], "expected items from seed + fixture"
    assert all(row["active"] is False for row in data["items"])
    # Inactive stock still holds value.
    assert Decimal(data["total_value"]) > 0
