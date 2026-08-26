"""Verification test for MC 650.10 (buy-side): C11/C12 suppliers + C18/C19 purchase.

Real executed checks:
  1. C12 POST   /api/suppliers  SupplierIn{name,email?,phone?,address?,payment_terms?}
                               -> SupplierOut                     [admin, procurement]
  2. C12 GET    /api/suppliers  -> list[SupplierOut]
  3. C12 GET    /api/suppliers/{id} -> SupplierOut
  4. C12 PUT    /api/suppliers/{id}
  5. Role gating: 401 missing token, 403 customer, 200 on admin/procurement
  6. Missing /api/suppliers/{id} -> 404
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token  # noqa: E402
from app.database import get_engine, init_db  # noqa: E402
from app.models import Supplier  # noqa: E402


def _make_app_client() -> TestClient:
    """App with ONLY the suppliers router mounted (isolated)."""
    from app.routers.suppliers import router as suppliers_router

    app = FastAPI()
    app.include_router(suppliers_router)
    return TestClient(app)


def _auth_header(role: str = "admin", uid: int = 10) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


def _seed_supplier(**overrides) -> Supplier:
    init_db()
    data = {
        "name": "Leverantör AB",
        "email": "order@lev.example",
        "phone": "031-111 22 33",
        "address": "Fabriksgatan 1, 411 27 Göteborg",
        "payment_terms": "30 dagar netto",
    }
    data.update(overrides)
    with Session(get_engine()) as s:
        sup = Supplier(**data)
        s.add(sup)
        s.commit()
        s.refresh(sup)
        return sup


# ---------------------------------------------------------------------------
# C12 — CRUD
# ---------------------------------------------------------------------------

def test_create_supplier_minimal():
    client = _make_app_client()
    resp = client.post(
        "/api/suppliers",
        json={"name": "Ny Leverantör"},
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Ny Leverantör"
    assert body["id"] >= 1
    assert body["email"] is None
    assert body["payment_terms"] is None


def test_create_supplier_full():
    client = _make_app_client()
    resp = client.post(
        "/api/suppliers",
        json={
            "name": "Full Lev AB",
            "email": "a@b.se",
            "phone": "08-123 45",
            "address": "Gata 1",
            "payment_terms": "14 dagar",
        },
        headers=_auth_header("procurement"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "a@b.se"
    assert body["payment_terms"] == "14 dagar"


def test_list_suppliers():
    _seed_supplier(name="AAA")
    _seed_supplier(name="BBB")
    client = _make_app_client()
    resp = client.get("/api/suppliers", headers=_auth_header("procurement"))
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()}
    assert {"AAA", "BBB"} <= names


def test_get_supplier_by_id():
    sup = _seed_supplier(name="LOOKUP")
    client = _make_app_client()
    resp = client.get(f"/api/suppliers/{sup.id}", headers=_auth_header("admin"))
    assert resp.status_code == 200
    assert resp.json()["name"] == "LOOKUP"


def test_get_supplier_missing_404():
    client = _make_app_client()
    resp = client.get("/api/suppliers/999999", headers=_auth_header("admin"))
    assert resp.status_code == 404


def test_update_supplier():
    sup = _seed_supplier(name="Before", payment_terms="0 dagar")
    client = _make_app_client()
    resp = client.put(
        f"/api/suppliers/{sup.id}",
        json={
            "name": "After AB",
            "email": "after@b.se",
            "phone": "08-999",
            "address": "Ny Gata 2",
            "payment_terms": "45 dagar",
        },
        headers=_auth_header("procurement"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "After AB"
    assert resp.json()["payment_terms"] == "45 dagar"


# ---------------------------------------------------------------------------
# Role gating (C12)
# ---------------------------------------------------------------------------

def test_suppliers_require_auth_401():
    client = _make_app_client()
    assert client.get("/api/suppliers").status_code == 401
    assert client.post("/api/suppliers", json={"name": "X"}).status_code == 401


def test_customer_role_forbidden_403():
    client = _make_app_client()
    resp = client.post("/api/suppliers", json={"name": "Cust"}, headers=_auth_header("customer"))
    assert resp.status_code == 403


def test_allowed_roles_create_200():
    client = _make_app_client()
    for role in ("admin", "procurement"):
        resp = client.post(
            "/api/suppliers",
            json={"name": f"Lev-{role}"},
            headers=_auth_header(role),
        )
        assert resp.status_code == 200, f"{role}: {resp.text}"
