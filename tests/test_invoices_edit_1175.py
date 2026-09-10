"""Tests for MC 1175.2 — invoices are rättningsbara: PATCH lines + makulera.

Surface added by this card:
  PATCH /api/invoices/{id}         {lines:[{item_id?,description?,qty}]} -> InvoiceOut
  PATCH /api/invoices/{id}/status  {status:"cancel"} -> InvoiceOut   (makulering)

Rules under test:
  * Line replacement is allowed on draft/issued (not paid); total re-sums
    server-side. Prices NEVER come from the client (C14): they carry over per
    item from the old server-owned lines, never from the wire.
  * paid invoice -> 409 (money is settled; its correction path is payments),
    cancelled -> 410, unknown invoice/item -> 404, price smuggling -> 422.
  * Makulering (cancel) requires the invoice to be fully refunded first
    (net payments == 0.00); without refunds it is 409. It is terminal:
    re-cancel 409, edit 410, lifecycle re-entry 410, new payment 409.
  * finance/admin only; sales is 403 on both endpoints.
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
    """One customer + two items (known prices) for the invoice flow."""
    from app.models import Customer, Item

    ids = {}
    with Session(get_engine()) as s:
        cust = Customer(name="Test Kund AB", email="k@t.example")
        s.add(cust)
        s.flush()
        ids["customer_id"] = cust.id

        lap = Item(sku="IT-1172-LAP", name="Test Laptop",
                   unit_price=Decimal("1000.00"), qty_on_hand=5, active=True)
        mon = Item(sku="IT-1172-MON", name="Test Monitor",
                   unit_price=Decimal("2500.00"), qty_on_hand=10, active=True)
        s.add_all([lap, mon])
        s.commit()
        ids["laptop"], ids["laptop_price"] = lap.id, Decimal("1000.00")
        ids["monitor"], ids["monitor_price"] = mon.id, Decimal("2500.00")
    return ids


def _auth(client, role):
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _issued_invoice(client, seed_base, qty_laptop=2):
    """Order -> confirm -> invoice; return the invoice dict (status issued)."""
    body = {"customer_id": seed_base["customer_id"],
            "lines": [{"item_id": seed_base["laptop"], "qty": qty_laptop}]}
    oid = client.post("/api/orders", headers=_auth(client, "sales"),
                      json=body).json()["id"]
    assert client.post(f"/api/orders/{oid}/confirm",
                       headers=_auth(client, "sales")).status_code == 200
    inv = client.post(f"/api/orders/{oid}/invoice",
                      headers=_auth(client, "finance"))
    assert inv.status_code == 200, inv.text
    return inv.json()


def _pay(client, iid, amount):
    return client.post(f"/api/invoices/{iid}/payment", headers=_auth(client, "finance"),
                       json={"amount": str(amount), "method": "bank"})


# ---------------------------------------------------------------------------
# PATCH /api/invoices/{id} — replace lines on an issued invoice
# ---------------------------------------------------------------------------

def test_patch_line_qty_retotals(client, seed_base):
    inv = _issued_invoice(client, seed_base)
    resp = client.patch(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 3}]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Price carries over from the old line (1000.00), never from the client.
    assert body["lines"][0]["unit_price"] == "1000.00"
    assert body["total"] == "3000.00"
    # persisted, not just echoed
    assert client.get(f"/api/invoices/{inv['id']}",
                      headers=_auth(client, "finance")).json() == body


def test_patch_replaces_line_set(client, seed_base):
    inv = _issued_invoice(client, seed_base)
    resp = client.patch(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance"), json={
        "lines": [
            {"item_id": seed_base["laptop"], "qty": 1},
            {"item_id": seed_base["monitor"], "qty": 2},
        ]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {ln["item_id"] for ln in body["lines"]} == {seed_base["laptop"], seed_base["monitor"]}
    assert body["total"] == "6000.00"  # 1x1000 carried + 2x2500 (catalog at correction)


def test_patch_rejects_client_price(client, seed_base):
    inv = _issued_invoice(client, seed_base)
    resp = client.patch(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance"), json={
        "lines": [{"item_id": seed_base["laptop"], "qty": 1, "unit_price": "1.00"}]})
    assert resp.status_code == 422


def test_patch_free_line_keeps_old_price(client, seed_base):
    """An old description-copied line keeps its price through the rewrite."""
    from app.models import Invoice, InvoiceLine

    iid = _issued_invoice(client, seed_base)["id"]
    with Session(get_engine()) as s:
        s.add(InvoiceLine(invoice_id=iid, item_id=None, description="Extra arbete",
                          qty=1, unit_price=Decimal("500.00"),
                          line_total=Decimal("500.00")))
        inv = s.get(Invoice, iid)
        inv.total = Decimal("2500.00")
        s.commit()
    resp = client.patch(f"/api/invoices/{iid}", headers=_auth(client, "finance"), json={
        "lines": [
            {"item_id": seed_base["laptop"], "qty": 2},
            {"description": "Extra arbete", "qty": 2},
        ]})
    assert resp.status_code == 200, resp.text
    free = [ln for ln in resp.json()["lines"] if ln["item_id"] is None]
    assert free and free[0]["unit_price"] == "500.00"
    assert resp.json()["total"] == "3000.00"


def test_patch_paid_invoice_409(client, seed_base):
    inv = _issued_invoice(client, seed_base)
    assert _pay(client, inv["id"], inv["total"]).status_code == 200
    resp = client.patch(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 1}]})
    assert resp.status_code == 409


def test_patch_unknown_item_404_leaves_invoice_untouched(client, seed_base):
    inv = _issued_invoice(client, seed_base)
    resp = client.patch(f"/api/invoices/{inv['id']}", headers=_auth(client, "finance"),
                        json={"lines": [{"item_id": 99999, "qty": 1}]})
    assert resp.status_code == 404
    after = client.get(f"/api/invoices/{inv['id']}",
                       headers=_auth(client, "finance")).json()
    assert after["lines"] == inv["lines"]  # atomic: nothing was replaced


def test_patch_unknown_invoice_404(client, seed_base):
    resp = client.patch("/api/invoices/99999", headers=_auth(client, "finance"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 1}]})
    assert resp.status_code == 404


def test_patch_empty_lines_and_zero_qty_422(client, seed_base):
    iid = _issued_invoice(client, seed_base)["id"]
    h = _auth(client, "finance")
    assert client.patch(f"/api/invoices/{iid}", headers=h,
                        json={"lines": []}).status_code == 422
    assert client.patch(f"/api/invoices/{iid}", headers=h,
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 0}]}).status_code == 422


def test_patch_sales_forbidden(client, seed_base):
    iid = _issued_invoice(client, seed_base)["id"]
    resp = client.patch(f"/api/invoices/{iid}", headers=_auth(client, "sales"),
                        json={"lines": [{"item_id": seed_base["laptop"], "qty": 1}]})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/invoices/{id}/status {status:"cancel"} — makulera
# ---------------------------------------------------------------------------

def test_cancel_requires_full_refund_first(client, seed_base):
    inv = _issued_invoice(client, seed_base)
    # Not paid, not refunded: nothing blocks makulering.
    resp = client.patch(f"/api/invoices/{inv['id']}/status", headers=_auth(client, "finance"),
                        json={"status": "cancel"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


def test_cancel_with_payments_409(client, seed_base):
    inv = _issued_invoice(client, seed_base)
    assert _pay(client, inv["id"], "500.00").status_code == 200
    resp = client.patch(f"/api/invoices/{inv['id']}/status", headers=_auth(client, "finance"),
                        json={"status": "cancel"})
    assert resp.status_code == 409


def test_cancel_after_refund_cycle(client, seed_base):
    """Paid -> refund (negative payment) -> net 0 -> makulering allowed."""
    from app.models import Payment
    from app.database import get_engine as ge

    inv = _issued_invoice(client, seed_base)
    assert _pay(client, inv["id"], inv["total"]).status_code == 200
    assert client.patch(f"/api/invoices/{inv['id']}/status",
                        headers=_auth(client, "finance"),
                        json={"status": "cancel"}).status_code == 409
    # T3 (payment cancellation) does not exist yet: simulate its net-zeroing
    # effect directly — a refund row of -total leaves sum(payments) == 0.
    with Session(ge()) as s:
        src = s.query(Payment).filter(Payment.invoice_id == inv["id"]).first()
        s.add(Payment(invoice_id=inv["id"], amount=-Decimal(src.amount),
                      method=src.method, paid_at=src.paid_at))
        s.commit()
    resp = client.patch(f"/api/invoices/{inv['id']}/status", headers=_auth(client, "finance"),
                        json={"status": "cancel"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


def test_cancel_is_terminal(client, seed_base):
    iid = _issued_invoice(client, seed_base)["id"]
    h = _auth(client, "finance")
    client.patch(f"/api/invoices/{iid}/status", headers=h, json={"status": "cancel"})
    assert client.patch(f"/api/invoices/{iid}/status", headers=h,
                        json={"status": "cancel"}).status_code == 409
    assert client.patch(f"/api/invoices/{iid}/status", headers=h,
                        json={"status": "issued"}).status_code == 410
    assert client.patch(f"/api/invoices/{iid}", headers=h,
                        json={"lines": [{"item_id": 1, "qty": 1}]}).status_code == 410
    assert _pay(client, iid, "100.00").status_code == 409


def test_cancel_unknown_invoice_404(client):
    resp = client.patch("/api/invoices/99999/status", headers=_auth(client, "finance"),
                        json={"status": "cancel"})
    assert resp.status_code == 404


def test_cancel_sales_forbidden(client, seed_base):
    iid = _issued_invoice(client, seed_base)["id"]
    resp = client.patch(f"/api/invoices/{iid}/status", headers=_auth(client, "sales"),
                        json={"status": "cancel"})
    assert resp.status_code == 403


def test_existing_lifecycle_still_works(client, seed_base):
    """MC 1175.2 must not break draft -> issued -> paid (test_invoices suite
    covers the basics; this pins one forward move on a fresh invoice)."""
    iid = _issued_invoice(client, seed_base)["id"]
    resp = client.patch(f"/api/invoices/{iid}/status", headers=_auth(client, "finance"),
                        json={"status": "paid"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "paid"
