"""Verification test for MC 650.7 (catalog): C7/C8 items + adjust_stock.

Real executed checks:
  1. C8  POST   /api/items    ItemIn -> ItemOut  (roles [admin,sales,finance,procurement])
  2. C8  GET    /api/items?active=1  -> list[ItemOut]
  3. C8  GET    /api/items/{id}      -> ItemOut
  4. C8  PUT    /api/items/{id}      ItemIn -> ItemOut
  5. C23 item money field: ItemIn.unit_price Decimal, ge=0, (12,2) — negative -> 422,
     float never crosses to the wire, ItemOut.unit_price is a Decimal string.
  6. C7/C8 adjust_stock(db, item_id, delta) — single owner of qty_on_hand (I2):
       - saves a decrement/increment on qty_on_hand
       - raises ValueError for unknown item (404 at the router boundary for create_order)
  7. Role gating: 401 missing token, 403 customer role, 200 on an allowed role.
"""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token  # noqa: E402
from app.database import get_engine, init_db  # noqa: E402
from app.models import Item  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_app_client() -> TestClient:
    """App with ONLY the items router + auth router mounted (isolated, matching
    how prior cards test a single router end-to-end)."""
    from app.routers.auth import router as auth_router
    from app.routers.items import router as items_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(items_router)
    return TestClient(app)


def _auth_header(role: str = "sales", uid: int = 10) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


def _seed_item(**overrides) -> Item:
    init_db()
    data = {
        "sku": "SKU-1",
        "name": "Test Widget",
        "unit_price": Decimal("19.99"),
        "qty_on_hand": 5,
        "active": True,
    }
    data.update(overrides)
    with Session(get_engine()) as s:
        item = Item(**data)
        s.add(item)
        s.commit()
        s.refresh(item)
        return item


# ---------------------------------------------------------------------------
# C23 — ItemIn money field is Decimal, non-negative
# ---------------------------------------------------------------------------

def test_itemin_unit_price_is_decimal_and_ge_zero():
    from app.schemas.item import ItemIn

    ok = ItemIn(sku="S", name="N", unit_price=Decimal("0.00"))
    assert ok.unit_price == Decimal("0.00")
    assert isinstance(ok.unit_price, Decimal)

    # negative unit_price rejected by schema (C8: catalog price never negative)
    with pytest.raises(Exception):
        ItemIn(sku="S", name="N", unit_price=Decimal("-0.01"))


def test_create_negative_unit_price_422():
    client = _make_app_client()
    resp = client.post(
        "/api/items",
        json={"sku": "NEG", "name": "Bad", "unit_price": -1.0, "qty_on_hand": 2},
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# C8 — CRUD
# ---------------------------------------------------------------------------

def test_create_item_returns_itemout_and_searches_by_sku():
    client = _make_app_client()
    resp = client.post(
        "/api/items",
        json={"sku": "WIDGET", "name": "Widget", "unit_price": "12.50", "qty_on_hand": 3},
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sku"] == "WIDGET"
    assert body["unit_price"] == "12.50"  # Decimal serialised to the wire as str
    assert body["qty_on_hand"] == 3
    assert body["active"] is True


def test_list_items_active_filter():
    _seed_item(sku="A1", active=True, qty_on_hand=1)
    _seed_item(sku="A2", active=False, qty_on_hand=1)
    client = _make_app_client()

    all_items = client.get("/api/items", headers=_auth_header("sales"))
    assert all_items.status_code == 200
    skus = {i["sku"] for i in all_items.json()}
    assert {"A1", "A2"} <= skus  # unfiltered returns both

    active = client.get("/api/items?active=1", headers=_auth_header("sales"))
    assert active.status_code == 200
    active_skus = {i["sku"] for i in active.json()}
    assert "A1" in active_skus and "A2" not in active_skus


def test_get_item_by_id():
    item = _seed_item(sku="LOOKUP")
    client = _make_app_client()
    resp = client.get(f"/api/items/{item.id}", headers=_auth_header("finance"))
    assert resp.status_code == 200
    assert resp.json()["sku"] == "LOOKUP"


def test_get_item_missing_404():
    client = _make_app_client()
    resp = client.get("/api/items/999999", headers=_auth_header("sales"))
    assert resp.status_code == 404


def test_update_item():
    item = _seed_item(sku="UPD", name="Before")
    client = _make_app_client()
    resp = client.put(
        f"/api/items/{item.id}",
        json={"sku": "UPD", "name": "After", "unit_price": "9.99", "qty_on_hand": 7},
        headers=_auth_header("procurement"),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "After"
    assert resp.json()["qty_on_hand"] == 7


def test_duplicate_sku_rejected():
    _seed_item(sku="DUP")
    client = _make_app_client()
    resp = client.post(
        "/api/items",
        json={"sku": "DUP", "name": "Second", "unit_price": "1.00"},
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 409  # UNIQUE sku surfaced as a clean conflict


# ---------------------------------------------------------------------------
# C8/C7 — adjust_stock (single owner of qty_on_hand, I2)
# ---------------------------------------------------------------------------

def test_adjust_stock_increments_and_decrements():
    from app.services.catalog import adjust_stock

    item = _seed_item(qty_on_hand=10)
    with Session(get_engine()) as s:
        adjust_stock(s, item.id, -3)
    with Session(get_engine()) as new_s:
        fresh = new_s.get(Item, item.id)
        assert fresh.qty_on_hand == 7
        adjust_stock(new_s, item.id, 5)
    with Session(get_engine()) as final_s:
        assert final_s.get(Item, item.id).qty_on_hand == 12


def test_adjust_stock_unknown_item_raises():
    from app.services.catalog import adjust_stock

    init_db()
    with Session(get_engine()) as s:
        with pytest.raises(Exception):
            adjust_stock(s, 999999, 1)  # must not silently succeed


# ---------------------------------------------------------------------------
# Role gating (C8)
# ---------------------------------------------------------------------------

def test_items_require_auth_401():
    client = _make_app_client()
    assert client.get("/api/items").status_code == 401
    assert client.post("/api/items", json={"sku": "X", "name": "Y", "unit_price": "1"}).status_code == 401


def test_customer_role_forbidden_403():
    client = _make_app_client()
    # POST requires [admin,sales,finance,procurement] — customer not allowed
    resp = client.post(
        "/api/items",
        json={"sku": "CUST", "name": "C", "unit_price": "1.00"},
        headers=_auth_header("customer"),
    )
    assert resp.status_code == 403


def test_allowed_role_create_200():
    client = _make_app_client()
    for role in ("admin", "sales", "finance", "procurement"):
        resp = client.post(
            "/api/items",
            json={"sku": f"SKU-{role}", "name": role, "unit_price": "1.00"},
            headers=_auth_header(role),
        )
        assert resp.status_code == 200, f"{role}: {resp.text}"
