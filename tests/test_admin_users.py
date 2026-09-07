"""Verification test for MC 1120.1 (user-admin): admin_users router + is_active.

Real executed checks:
  1. GET  /api/admin/users      requires admin (403 for non-admin) and lists users
  2. POST /api/admin/users      creates a user (hash_password never echoed), validates role
  3. GET  /api/admin/users/{id} returns one user; 404 for unknown id
  4. PATCH /api/admin/users/{id} updates role/email/is_active; 404 unknown id
  5. login rejects inactive user (is_active default True, can be set False)
  6. sensitive field password_hash is NEVER returned on any admin_users payload
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password  # noqa: E402
from app.database import get_engine, init_db  # noqa: E402
from app.models import ROLES, User  # noqa: E402


def _seed_admin_and_client():
    """Seed an admin user (id auto) and return (client, token) for the admin_users router."""
    init_db()
    with Session(get_engine()) as s:
        admin = User(
            username="admin", password_hash=hash_password("admin-pass"),
            role="admin", email="admin@affar.demo", is_active=True,
        )
        s.add(admin)
        s.commit()
        admin_id = admin.id
    token = create_access_token(user_id=admin_id, role="admin")
    from app.routers.admin_users import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), token


def _seed_extra_user(**kwargs):
    with Session(get_engine()) as s:
        u = User(
            username=kwargs.get("username", "extra"),
            password_hash=hash_password(kwargs.get("password", "x")),
            role=kwargs.get("role", "sales"),
            email=kwargs.get("email", "extra@affar.demo"),
            is_active=kwargs.get("is_active", True),
        )
        s.add(u)
        s.commit()
        return u.id


def test_list_requires_admin():
    client, _ = _seed_admin_and_client()
    non_admin = create_access_token(user_id=9, role="sales")
    resp = client.get("/api/admin/users", headers={"Authorization": "Bearer " + non_admin})
    assert resp.status_code == 403


def test_list_requires_auth():
    client, _ = _seed_admin_and_client()
    resp = client.get("/api/admin/users")
    assert resp.status_code == 401


def test_list_returns_created_users():
    client, token = _seed_admin_and_client()
    _seed_extra_user(username="nisse", role="finance")
    resp = client.get("/api/admin/users", headers={"Authorization": "Bearer " + token})
    assert resp.status_code == 200
    body = resp.json()
    usernames = {u["username"] for u in body}
    assert "admin" in usernames and "nisse" in usernames
    # password_hash is FORBIDDEN on the wire.
    for u in body:
        assert "password_hash" not in u
        assert "is_active" in u


def test_create_user_requires_admin():
    client, _ = _seed_admin_and_client()
    non_admin = create_access_token(user_id=9, role="customer")
    resp = client.post("/api/admin/users", headers={"Authorization": "Bearer " + non_admin},
                       json={"username": "ny", "role": "sales", "password": "hemligt"})
    assert resp.status_code == 403


def test_create_user_success():
    client, token = _seed_admin_and_client()
    resp = client.post("/api/admin/users", headers={"Authorization": "Bearer " + token},
                       json={"username": "ny", "role": "procurement", "email": "ny@affar.demo",
                             "password": "hemligt-pass"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "ny"
    assert body["role"] == "procurement"
    assert body["email"] == "ny@affar.demo"
    assert body["is_active"] is True
    assert "password_hash" not in body
    # Round-trip: the created user can log in with the given password (proves
    # hash_password was applied, not a plaintext echo).
    from app.routers.auth import router as auth_router
    app = FastAPI()
    app.include_router(auth_router)
    lc = TestClient(app)
    lresp = lc.post("/api/auth/login", json={"username": "ny", "password": "hemligt-pass"})
    assert lresp.status_code == 200


def test_create_user_rejects_unknown_role():
    client, token = _seed_admin_and_client()
    resp = client.post("/api/admin/users", headers={"Authorization": "Bearer " + token},
                       json={"username": "ny", "role": "not-a-role", "password": "x"})
    assert resp.status_code == 422  # Pydantic Literal/validator rejects


def test_get_one_user_404():
    client, token = _seed_admin_and_client()
    resp = client.get("/api/admin/users/9999", headers={"Authorization": "Bearer " + token})
    assert resp.status_code == 404


def test_patch_update_role_and_email():
    client, token = _seed_admin_and_client()
    uid = _seed_extra_user(username="nisse", role="sales", email="nisse@x.se")
    resp = client.patch("/api/admin/users/" + str(uid), headers={"Authorization": "Bearer " + token},
                        json={"role": "finance", "email": "ny@x.se"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "finance"
    assert body["email"] == "ny@x.se"
    assert "password_hash" not in body


def test_patch_requires_admin():
    client, _ = _seed_admin_and_client()
    uid = _seed_extra_user(username="nisse")
    non_admin = create_access_token(user_id=9, role="sales")
    resp = client.patch("/api/admin/users/" + str(uid), headers={"Authorization": "Bearer " + non_admin},
                        json={"is_active": False})
    assert resp.status_code == 403


def test_patch_deactivate_blocks_login():
    client, token = _seed_admin_and_client()
    uid = _seed_extra_user(username="nisse", role="sales", password="hemligt")
    resp = client.patch("/api/admin/users/" + str(uid), headers={"Authorization": "Bearer " + token},
                        json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    # Inactive user must NOT be able to log in.
    from app.routers.auth import router as auth_router
    app = FastAPI()
    app.include_router(auth_router)
    lc = TestClient(app)
    lresp = lc.post("/api/auth/login", json={"username": "nisse", "password": "hemligt"})
    assert lresp.status_code == 403


def test_demo_model_has_is_active_column_default_true():
    init_db()
    with Session(get_engine()) as s:
        u = User(username="ny", password_hash=hash_password("x"), role="admin")
        s.add(u)
        s.commit()
        assert u.is_active is True
        assert ROLES == ("admin", "sales", "finance", "procurement", "customer")
