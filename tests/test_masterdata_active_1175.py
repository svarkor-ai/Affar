"""Verification test for MC 1175.5 (masterdata): is_active avaktivering.

Real executed checks:
  1. PATCH /api/items/{id}/active  toggles Item.active; ?active=1 hides the
     deactivated article, ?active=0 shows it (same column as C8 filter)
  2. PATCH /api/customers/{id}/active toggles is_active (CustomerOut field)
  3. PATCH /api/suppliers/{id}/active toggles is_active (SupplierOut field)
  4. Deactivated customer: NEW order -> 410; existing draft order unaffected
  5. Deactivated supplier: NEW PO -> 410
  6. Reactivation restores orderability (round-trip)
  7. Strict wire: PUT bodies reject is_active (extra=forbid -> 422);
     PATCH /active rejects extra keys (ActivePatch extra=forbid -> 422)
  8. RBAC: sales 403 on supplier active-PATCH, procurement 403 on customer
     active-PATCH, anonymous 401
  9. Unknown id -> 404
"""

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.database import get_engine, init_db


def _client() -> TestClient:
    from app.routers.admin_users import router as admin_users_router
    from app.routers.auth import router as auth_router
    from app.routers.customers import router as customers_router
    from app.routers.items import router as items_router
    from app.routers.orders import router as orders_router
    from app.routers.purchase import router as purchase_router
    from app.routers.suppliers import router as suppliers_router

    app = FastAPI()
    for r in (
        auth_router, items_router, customers_router, suppliers_router,
        orders_router, purchase_router, admin_users_router,
    ):
        app.include_router(r)
    return TestClient(app)


def _hdr(role: str, uid: int = 1) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


def _mk_item(client, sku="SKU-A1175") -> int:
    r = client.post("/api/items", headers=_hdr("admin"), json={
        "sku": sku, "name": "Artikel 1175", "unit_price": "10.00",
        "qty_on_hand": 5,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_customer(client) -> int:
    r = client.post("/api/customers", headers=_hdr("sales"), json={"name": "Kund 1175"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mk_supplier(client) -> int:
    r = client.post("/api/suppliers", headers=_hdr("admin"), json={"name": "Lev 1175"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_item_active_patch_filters_listing():
    init_db()
    c = _client()
    iid = _mk_item(c)
    assert c.get(f"/api/items/{iid}", headers=_hdr("admin")).json()["is_active"] is True
    assert c.get(f"/api/items/{iid}", headers=_hdr("admin")).json()["active"] is True

    r = c.patch(f"/api/items/{iid}/active", headers=_hdr("admin"),
                json={"is_active": False})
    assert r.status_code == 200 and r.json()["active"] is False

    active_ids = [i["id"] for i in c.get("/api/items?active=1",
                                         headers=_hdr("admin")).json()]
    assert iid not in active_ids
    inactive_ids = [i["id"] for i in c.get("/api/items?active=0",
                                           headers=_hdr("admin")).json()]
    assert iid in inactive_ids

    # reactivation round-trip
    r = c.patch(f"/api/items/{iid}/active", headers=_hdr("admin"),
                json={"is_active": True})
    assert r.status_code == 200 and r.json()["is_active"] is True


def test_customer_supplier_flags_on_wire_and_roundtrip():
    init_db()
    c = _client()
    cid, sid = _mk_customer(c), _mk_supplier(c)
    assert c.get(f"/api/customers/{cid}", headers=_hdr("sales")).json()["is_active"] is True
    assert c.get(f"/api/suppliers/{sid}", headers=_hdr("procurement")).json()["is_active"] is True

    r = c.patch(f"/api/customers/{cid}/active", headers=_hdr("sales"),
                json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    r = c.patch(f"/api/suppliers/{sid}/active", headers=_hdr("procurement"),
                json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False


def test_deactivated_customer_blocked_from_new_orders():
    init_db()
    c = _client()
    iid, cid = _mk_item(c), _mk_customer(c)

    def _order():
        return c.post("/api/orders", headers=_hdr("sales"), json={
            "customer_id": cid, "lines": [{"item_id": iid, "qty": 2}]})

    ok = _order()
    assert ok.status_code == 200, ok.text
    oid = ok.json()["id"]

    c.patch(f"/api/customers/{cid}/active", headers=_hdr("admin"),
            json={"is_active": False})
    blocked = _order()
    assert blocked.status_code == 410, blocked.text

    # existing draft order is untouched — still readable/editable
    assert c.get(f"/api/orders/{oid}", headers=_hdr("sales")).status_code == 200

    # reactivation restores orderability
    c.patch(f"/api/customers/{cid}/active", headers=_hdr("admin"),
            json={"is_active": True})
    assert _order().status_code == 200


def test_deactivated_supplier_blocked_from_new_pos():
    init_db()
    c = _client()
    iid, sid = _mk_item(c), _mk_supplier(c)

    def _po():
        return c.post("/api/purchase-orders", headers=_hdr("procurement"), json={
            "supplier_id": sid,
            "lines": [{"item_id": iid, "qty": 1, "unit_cost": "5.00"}]})

    assert _po().status_code == 200
    c.patch(f"/api/suppliers/{sid}/active", headers=_hdr("admin"),
            json={"is_active": False})
    r = _po()
    assert r.status_code == 410, r.text


def test_strict_wire_extra_keys_rejected():
    init_db()
    c = _client()
    iid, cid, sid = _mk_item(c), _mk_customer(c), _mk_supplier(c)

    # active-PATCH carries ONLY is_active
    assert c.patch(f"/api/items/{iid}/active", headers=_hdr("admin"),
                   json={"is_active": False, "name": "x"}).status_code == 422
    assert c.patch(f"/api/customers/{cid}/active", headers=_hdr("sales"),
                   json={"is_active": False, "name": "x"}).status_code == 422
    # plain PUT never flips the flag (schema has no is_active field)
    assert c.put(f"/api/customers/{cid}", headers=_hdr("sales"),
                 json={"name": "Kund 1175", "is_active": False}).status_code == 422
    assert c.put(f"/api/suppliers/{sid}", headers=_hdr("procurement"),
                 json={"name": "Lev 1175", "is_active": False}).status_code == 422
    # PUT never flipped it — still active
    assert c.get(f"/api/customers/{cid}", headers=_hdr("sales")).json()["is_active"] is True


def test_rbac_and_404():
    init_db()
    c = _client()
    cid, sid = _mk_customer(c), _mk_supplier(c)

    # customer roles (C9 set) do not include procurement; supplier set not sales
    assert c.patch(f"/api/suppliers/{sid}/active", headers=_hdr("sales"),
                   json={"is_active": False}).status_code == 403
    assert c.patch(f"/api/customers/{cid}/active", headers=_hdr("procurement"),
                   json={"is_active": False}).status_code == 403
    assert c.patch(f"/api/customers/{cid}/active",
                   json={"is_active": False}).status_code == 401

    assert c.patch("/api/items/999999/active", headers=_hdr("admin"),
                   json={"is_active": False}).status_code == 404
    assert c.patch("/api/customers/999999/active", headers=_hdr("admin"),
                   json={"is_active": False}).status_code == 404
    assert c.patch("/api/suppliers/999999/active", headers=_hdr("admin"),
                   json={"is_active": False}).status_code == 404


def test_db_default_true_for_direct_rows():
    """A row inserted directly (pre-migration shape never omits the column —
    default True keeps legacy rows active)."""
    from app.models import Customer
    init_db()
    with Session(get_engine()) as s:
        cust = Customer(name="Direkt Kund")
        s.add(cust)
        s.commit()
        assert cust.is_active is True
