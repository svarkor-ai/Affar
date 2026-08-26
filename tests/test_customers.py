"""Verification test for MC 691.2 (R2): C9 customers router+service+schema.

Real executed checks:
  1. C9 POST   /api/customers  CustomerIn{name,email?,phone?,address?}
                              -> CustomerOut(id, name, email?, phone?, address?, created_at)
                              [admin, sales]
  2. C9 GET    /api/customers  -> list[CustomerOut]
  3. C9 GET    /api/customers/{id} -> CustomerOut
  4. C9 PUT    /api/customers/{id} CustomerIn -> CustomerOut
  5. Role gating: 401 missing token, 403 customer, 200 on admin/sales
  6. Missing /api/customers/{id} -> 404
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token  # noqa: E402
from app.database import get_engine, init_db  # noqa: E402
from app.models import Customer  # noqa: E402


def _make_app_client() -> TestClient:
    """App with ONLY the customers router mounted (isolated)."""
    from app.routers.customers import router as customers_router

    app = FastAPI()
    app.include_router(customers_router)
    return TestClient(app)


def _auth_header(role: str = "admin", uid: int = 10) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


def _seed_customer(**overrides) -> Customer:
    init_db()
    data = {
        "name": "Acme Demo AB",
        "email": "kund@acme.example",
        "phone": "08-555 01 02",
        "address": "DemoGatan 7, 111 37 Stockholm",
    }
    data.update(overrides)
    with Session(get_engine()) as s:
        cust = Customer(**data)
        s.add(cust)
        s.commit()
        s.refresh(cust)
        return cust


# ---------------------------------------------------------------------------
# C9 — CRUD
# ---------------------------------------------------------------------------

def test_create_customer_minimal():
    client = _make_app_client()
    resp = client.post(
        "/api/customers",
        json={"name": "Ny Kund AB"},
        headers=_auth_header("admin"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Ny Kund AB"
    assert body["id"] >= 1
    assert body["email"] is None
    assert "created_at" in body


def test_create_customer_full():
    client = _make_app_client()
    resp = client.post(
        "/api/customers",
        json={
            "name": "Full Kund AB",
            "email": "a@kund.se",
            "phone": "08-123 45",
            "address": "Gata 1, Stockholm",
        },
        headers=_auth_header("sales"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "a@kund.se"
    assert body["address"] == "Gata 1, Stockholm"


def test_list_customers():
    _seed_customer(name="AAA")
    _seed_customer(name="BBB")
    client = _make_app_client()
    resp = client.get("/api/customers", headers=_auth_header("sales"))
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert {"AAA", "BBB"} <= names


def test_get_customer_by_id():
    cust = _seed_customer(name="LOOKUP")
    client = _make_app_client()
    resp = client.get(f"/api/customers/{cust.id}", headers=_auth_header("admin"))
    assert resp.status_code == 200
    assert resp.json()["name"] == "LOOKUP"


def test_get_customer_missing_404():
    client = _make_app_client()
    resp = client.get("/api/customers/999999", headers=_auth_header("admin"))
    assert resp.status_code == 404


def test_update_customer():
    cust = _seed_customer(name="Before AB")
    client = _make_app_client()
    resp = client.put(
        f"/api/customers/{cust.id}",
        json={
            "name": "After AB",
            "email": "after@kund.se",
            "phone": "08-999",
            "address": "Ny Gata 2",
        },
        headers=_auth_header("sales"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "After AB"
    assert resp.json()["address"] == "Ny Gata 2"


# ---------------------------------------------------------------------------
# Role gating (C9)
# ---------------------------------------------------------------------------

def test_customers_require_auth_401():
    client = _make_app_client()
    assert client.get("/api/customers").status_code == 401
    assert client.post("/api/customers", json={"name": "X"}).status_code == 401


def test_customer_role_forbidden_403():
    client = _make_app_client()
    resp = client.post(
        "/api/customers",
        json={"name": "Cust"},
        headers=_auth_header("customer"),
    )
    assert resp.status_code == 403


def test_allowed_roles_create_200():
    client = _make_app_client()
    for role in ("admin", "sales"):
        resp = client.post(
            "/api/customers",
            json={"name": f"Kund-{role}"},
            headers=_auth_header(role),
        )
        assert resp.status_code == 200, f"{role}: {resp.text}"
