"""Verification test for MC 650.10 (buy-side): C18/C19 purchase orders.

Real executed checks:
  1. C18 model reuse — PurchaseOrder/PurchaseOrderLine already from app-models.
  2. C19 POST   /api/purchase-orders
      PurchaseOrderIn{supplier_id, lines:[{item_id, qty, unit_cost}]} -> POut
                                                        [admin, procurement]
      unit_cost validated server-side Decimal ge=0 (12,2); qty>0;
      line_total = qty*unit_cost computed server-side.
  3. C19 GET    /api/purchase-orders -> list[POut]
  4. C19 GET    /api/purchase-orders/{id} -> POut
  5. C19 PATCH  /api/purchase-orders/{id}/status {status}; on "received" ->
      catalog.adjust_stock(db, item, +qty) per line (stock-in, I2 single owner).
  6. Bound tests: negative unit_cost -> 422; zerofqty -> 422; bad status -> 422.
  7. Role gating: 401 missing, 403 customer, 200 admin/procurement.
  8. Missing supplier/item -> 404; missing PO -> 404.
"""

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token  # noqa: E402
from app.database import get_engine, init_db  # noqa: E402
from app.models import Item, PurchaseOrder, Supplier  # noqa: E402


def _make_app_client() -> TestClient:
    """App with ONLY the purchase router mounted (isolated)."""
    from app.routers.purchase import router as purchase_router

    app = FastAPI()
    app.include_router(purchase_router)
    return TestClient(app)


def _auth_header(role: str = "admin", uid: int = 10) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


def _seed_env(item_qty: int = 100) -> tuple[Supplier, Item]:
    """Seed one supplier + one item; return both PK-bearing ORM objects."""
    init_db()
    with Session(get_engine()) as s:
        sup = Supplier(name="Lev AB")
        item = Item(
            sku="IT-X1",
            name="Komponent X",
            unit_price=Decimal("10.00"),
            qty_on_hand=item_qty,
            active=True,
        )
        s.add_all([sup, item])
        s.commit()
        s.refresh(sup)
        s.refresh(item)
        return sup, item


def _po_payload(supplier_id: int, item_id: int, **line_overrides) -> dict:
    line = {"item_id": item_id, "qty": 4, "unit_cost": "25.50"}
    line.update(line_overrides)
    return {"supplier_id": supplier_id, "lines": [line]}


# ---------------------------------------------------------------------------
# C19 — create + read
# ---------------------------------------------------------------------------

def test_create_purchase_order_computes_line_total_server_side():
    sup, item = _seed_env()
    client = _make_app_client()
    resp = client.post(
        "/api/purchase-orders",
        json=_po_payload(sup.id, item.id),
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["supplier_id"] == sup.id
    lines = body["lines"]
    assert len(lines) == 1
    # line_total = qty * unit_cost = 4 * 25.50 = 102.00, computed server-side
    assert lines[0]["line_total"] == "102.00"
    assert lines[0]["unit_cost"] == "25.50"
    assert lines[0]["qty"] == 4


def test_list_purchase_orders():
    sup, item = _seed_env()
    client = _make_app_client()
    client.post("/api/purchase-orders", json=_po_payload(sup.id, item.id), headers=_auth_header("procurement"))
    resp = client.get("/api/purchase-orders", headers=_auth_header("procurement"))
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_purchase_order_by_id():
    sup, item = _seed_env()
    client = _make_app_client()
    created = client.post("/api/purchase-orders", json=_po_payload(sup.id, item.id), headers=_auth_header("admin")).json()
    resp = client.get(f"/api/purchase-orders/{created['id']}", headers=_auth_header("admin"))
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_purchase_order_missing_404():
    client = _make_app_client()
    assert client.get("/api/purchase-orders/999999", headers=_auth_header("admin")).status_code == 404


# ---------------------------------------------------------------------------
# C19 — bounds (C23/refutation 1+4): unit_cost Decimal, ge=0; qty>0
# ---------------------------------------------------------------------------

def test_negative_unit_cost_rejected_422():
    sup, item = _seed_env()
    client = _make_app_client()
    resp = client.post(
        "/api/purchase-orders",
        json=_po_payload(sup.id, item.id, qty=4, unit_cost="-1.00"),
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 422, resp.text


def test_zero_qty_rejected_422():
    sup, item = _seed_env()
    client = _make_app_client()
    resp = client.post(
        "/api/purchase-orders",
        json=_po_payload(sup.id, item.id, qty=0, unit_cost="1.00"),
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 422, resp.text


def test_missing_supplier_404():
    _, item = _seed_env()
    client = _make_app_client()
    resp = client.post(
        "/api/purchase-orders",
        json=_po_payload(999999, item.id),
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 404, resp.text


def test_missing_item_404():
    sup, _ = _seed_env()
    client = _make_app_client()
    resp = client.post(
        "/api/purchase-orders",
        json=_po_payload(sup.id, 999999),
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# C19 — status transitions, received -> stock-in (I2 single stock owner)
# ---------------------------------------------------------------------------

def test_received_patches_stock_in_on_items():
    sup, item = _seed_env(item_qty=10)
    client = _make_app_client()
    created = client.post(
        "/api/purchase-orders",
        json=_po_payload(sup.id, item.id, qty=5, unit_cost="8.00"),
        headers=_auth_header("procurement"),
    ).json()
    po_id = created["id"]

    resp = client.patch(f"/api/purchase-orders/{po_id}/status", json={"status": "received"},
                        headers=_auth_header("procurement"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "received"

    # stock-in: qty_on_hand went 10 -> 15 via catalog.adjust_stock(+qty)
    with Session(get_engine()) as s:
        fresh = s.get(Item, item.id)
    assert fresh.qty_on_hand == 15


def test_ordered_status_transition_no_stock_change():
    sup, item = _seed_env(item_qty=10)
    client = _make_app_client()
    created = client.post(
        "/api/purchase-orders",
        json=_po_payload(sup.id, item.id, qty=5, unit_cost="8.00"),
        headers=_auth_header("admin"),
    ).json()
    resp = client.patch(f"/api/purchase-orders/{created['id']}/status", json={"status": "ordered"},
                        headers=_auth_header("admin"))
    assert resp.status_code == 200
    with Session(get_engine()) as s:
        assert s.get(Item, item.id).qty_on_hand == 10  # unchanged


def test_invalid_status_rejected_422():
    sup, item = _seed_env()
    client = _make_app_client()
    created = client.post("/api/purchase-orders", json=_po_payload(sup.id, item.id), headers=_auth_header("admin")).json()
    resp = client.patch(f"/api/purchase-orders/{created['id']}/status", json={"status": "nonsense"},
                        headers=_auth_header("admin"))
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Role gating (C19)
# ---------------------------------------------------------------------------

def test_purchase_require_auth_401():
    client = _make_app_client()
    assert client.get("/api/purchase-orders").status_code == 401
    assert client.post("/api/purchase-orders", json={"supplier_id": 1, "lines": []}).status_code == 401


def test_customer_role_forbidden_403():
    client = _make_app_client()
    resp = client.post(
        "/api/purchase-orders",
        json={"supplier_id": 1, "lines": []},
        headers=_auth_header("customer"),
    )
    assert resp.status_code == 403


def test_allowed_roles_create_200():
    _, item = _seed_env()
    with Session(get_engine()) as s:
        sup = Supplier(name="Lev Own")
        s.add(sup)
        s.commit()
        s.refresh(sup)
    client = _make_app_client()
    for role in ("admin", "procurement"):
        resp = client.post(
            "/api/purchase-orders",
            json=_po_payload(sup.id, item.id, unit_cost="1.00"),
            headers=_auth_header(role),
        )
        assert resp.status_code == 200, f"{role}: {resp.text}"
