"""Verification test for MC 650.3 (app-auth): C4 auth primitives + C6 router.

Real executed checks:
  1. C4 hash_password / check_password round-trip (and mismatch)
  2. C4 create_access_token / verify_token round-trip -> {user_id, role}
  3. C4 verify_token returns None for garbage / tampered tokens
  4. C4 require_role dependency: 401 (missing/invalid/expired), 403 (wrong role),
     200 (allowed role) — exercised through a tiny protected FastAPI app
  5. C6 POST /api/auth/login  correct creds -> TokenResponse; wrong -> 401
  6. C6 GET  /api/auth/me     valid Bearer -> UserOut; missing/invalid -> 401
"""

import time

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import (  # noqa: E402
    ROLES,
    check_password,
    create_access_token,
    hash_password,
    require_role,
    verify_token,
)
from app.database import get_engine, init_db  # noqa: E402
from app.models import User  # noqa: E402


# ---------------------------------------------------------------------------
# C4 — password hashing
# ---------------------------------------------------------------------------


def test_hash_and_check_password_roundtrip():
    hashed = hash_password("hemligt-lösenord")
    assert hashed.startswith("$2b$")
    assert hashed != "hemligt-lösenord"
    assert check_password("hemligt-lösenord", hashed) is True


def test_check_password_wrong_value():
    hashed = hash_password("rätt")
    assert check_password("fel", hashed) is False


def test_hash_is_salted_per_call():
    # Two hashes of the same password must differ (not deterministic).
    assert hash_password("samma") != hash_password("samma")


# ---------------------------------------------------------------------------
# C4 — JWT helpers
# ---------------------------------------------------------------------------


def test_create_and_verify_token_roundtrip():
    token = create_access_token(user_id=7, role="finance")
    payload = verify_token(token)
    assert payload == {"user_id": 7, "role": "finance"}


def test_verify_token_rejects_garbage():
    assert verify_token("not-a-real-jwt") is None


def test_verify_token_rejects_tampered():
    token = create_access_token(user_id=1, role="admin")
    # Flip a char in the payload region -> signature mismatch -> None
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    assert verify_token(tampered) is None


# ---------------------------------------------------------------------------
# C4 — require_role dependency
# ---------------------------------------------------------------------------

_guard_app = FastAPI()


@_guard_app.get("/admin")
def _admin(current: dict = Depends(require_role(["admin"]))):
    return current


@_guard_app.get("/finance-or-admin")
def _fin(current: dict = Depends(require_role(["finance", "admin"]))):
    return current


def test_require_role_missing_token_401():
    client = TestClient(_guard_app)
    resp = client.get("/admin")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


def test_require_role_invalid_token_401():
    client = TestClient(_guard_app)
    resp = client.get("/admin", headers={"Authorization": "Bearer garbage.token.here"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired token"


def test_require_role_not_allowed_403():
    client = TestClient(_guard_app)
    token = create_access_token(user_id=2, role="sales")  # not in [admin]
    resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Insufficient permissions"


def test_require_role_allowed_multi_200():
    client = TestClient(_guard_app)
    token = create_access_token(user_id=3, role="finance")
    resp = client.get("/finance-or-admin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "finance"


def test_require_role_expired_token_401():
    # Deterministic expiry check: sign a payload whose exp is already in the
    # past with the SAME library+secret the app uses (jose) -> verify_token
    # must return None -> 401.
    from datetime import UTC, datetime, timedelta

    from jose import jwt as jose_jwt

    from app import config as _cfg

    now = datetime.now(UTC)
    expired_payload = {
        "sub": "9",
        "role": "admin",
        "exp": now - timedelta(seconds=1),
        "iat": now - timedelta(minutes=2),
    }
    expired = jose_jwt.encode(
        expired_payload, _cfg.SECRET_KEY, algorithm=_cfg.JWT_ALGORITHM
    )
    client = TestClient(_guard_app)
    resp = client.get("/admin", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired token"


def test_roles_closed_set_matches_cf():
    # C-F fixed point: identical closed set to the User model's ROLES.
    assert ROLES == ("admin", "sales", "finance", "procurement", "customer")
    from app.models import ROLES as model_roles

    assert ROLES == model_roles


# ---------------------------------------------------------------------------
# C6 — login + me endpoints
# ---------------------------------------------------------------------------


def _seed_user(username="demo", password="lösenord", role="sales"):
    init_db()
    with Session(get_engine()) as s:
        u = User(username=username, password_hash=hash_password(password), role=role)
        s.add(u)
        s.commit()
        return u.id


def _make_app_client():
    from app.routers.auth import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_login_success_returns_token_and_user():
    _seed_user()
    client = _make_app_client()
    resp = client.post(
        "/api/auth/login",
        json={"username": "demo", "password": "lösenord"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert verify_token(body["access_token"])["role"] == "sales"
    assert body["user"] == {"id": body["user"]["id"], "username": "demo", "role": "sales"}


def test_login_wrong_password_401():
    _seed_user()
    client = _make_app_client()
    resp = client.post(
        "/api/auth/login",
        json={"username": "demo", "password": "fel-lösenord"},
    )
    assert resp.status_code == 401


def test_login_unknown_user_401():
    client = _make_app_client()
    resp = client.post(
        "/api/auth/login",
        json={"username": "finns-inte", "password": "x"},
    )
    assert resp.status_code == 401


def test_me_valid_token_returns_userout():
    uid = _seed_user()
    client = _make_app_client()
    token = create_access_token(user_id=uid, role="sales")
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"id": uid, "username": "demo", "role": "sales"}


def test_me_missing_token_401():
    client = _make_app_client()
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_invalid_token_401():
    uid = _seed_user()
    client = _make_app_client()
    token = create_access_token(user_id=uid, role="sales")
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}xxxx"}
    )
    assert resp.status_code == 401
