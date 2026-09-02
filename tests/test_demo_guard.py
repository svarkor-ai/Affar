"""Tests for MC 707.2 G3: public demo write guard (hotell pattern, MC 2034.2)."""

import importlib

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import get_engine, init_db
from app.models import User


def _client():
    create_app = importlib.import_module("app.main").create_app
    return TestClient(create_app())


# Login creds used only inside these tests (not a production account).
PASSWD = "demo-suite-passwd"


def _seed_user(username):
    """Seed a real user in the test DB (pattern from tests/test_auth.py).

    The app has no /api/auth/register endpoint — only /api/auth/login and
    /api/auth/me — so the test creates the user directly in the database.
    """
    init_db()
    with Session(get_engine()) as s:
        u = User(username=username, password_hash=hash_password(PASSWD), role="sales")
        s.add(u)
        s.commit()


def _login(client, username):
    _seed_user(username)
    res = client.post("/api/auth/login", json={"username": username, "password": PASSWD})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _item_payload(name):
    # ItemIn wire contract (app/schemas/item.py): sku + name + unit_price.
    return {"sku": name, "name": name, "unit_price": 10.0}


def test_guard_module_exists_with_expected_shape():
    mod = importlib.import_module("app.demo_guard")
    assert hasattr(mod, "DemoWriteGuard")
    assert hasattr(mod, "visitor_ip")
    assert set(mod.WRITE_METHODS) == {"POST", "PUT", "PATCH", "DELETE"}


def test_guard_mounted_on_app():
    client = _client()
    # app.middleware is a bound method in this starlette version; the
    # middleware list lives on app.user_middleware. Tolerate both shapes.
    mws = [
        m.cls.__name__
        for m in getattr(client.app, "user_middleware", client.app.middleware)
    ]
    assert "DemoWriteGuard" in mws, mws


def test_writes_are_throttled_per_visitor_429():
    mod = importlib.import_module("app.demo_guard")
    guard = mod.DemoWriteGuard(app=lambda *a, **k: None, capacity=3, window=300.0)
    results = [guard._take("9.9.9.9") for _ in range(5)]
    assert results == [True, True, True, False, False]


def test_429_end_to_end_over_http(monkeypatch):
    """Flood POSTs from one visitor: the first few succeed, later ones 429."""
    mod = importlib.import_module("app.demo_guard")
    # create_app mounts DemoWriteGuard reading the module default at mount
    # time, so patching the constant BEFORE create_app() is enough.
    monkeypatch.setattr(mod, "CAPACITY", 3)

    create_app = importlib.import_module("app.main").create_app
    client = TestClient(create_app())
    auth = _login(client, "guard-flood-1")

    codes = []
    for i in range(6):
        r = client.post(
            "/api/items",
            json=_item_payload(f"guard-item-{i}"),
            headers={"Authorization": "Bearer " + auth, "CF-Connecting-IP": "203.0.113.7"},
        )
        codes.append(r.status_code)
    # POST /api/items returns 200 (router has no status_code override).
    assert codes[0] == 200, codes
    assert 429 in codes, codes
    blocked = client.post(
        "/api/items",
        json=_item_payload("guard-item-blocked"),
        headers={"Authorization": "Bearer " + auth, "CF-Connecting-IP": "203.0.113.7"},
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after"), "429 must carry Retry-After"


def test_other_visitors_unthrottled():
    mod = importlib.import_module("app.demo_guard")
    guard = mod.DemoWriteGuard(app=lambda *a, **k: None, capacity=2, window=300.0)
    # Exhaust one visitor's writes...
    assert guard._take("1.1.1.1") and guard._take("1.1.1.1")
    assert not guard._take("1.1.1.1")
    # ...another visitor is unaffected (per-visitor key).
    assert guard._take("2.2.2.2")


def test_visitor_ip_precedence():
    mod = importlib.import_module("app.demo_guard")
    assert mod.visitor_ip(_FakeReq({"cf-connecting-ip": "9.9.9.9"}, None)) == "9.9.9.9"
    assert mod.visitor_ip(_FakeReq({"x-forwarded-for": "8.8.8.8, 10.0.0.1"}, None)) == "8.8.8.8"
    assert mod.visitor_ip(_FakeReq({}, _Client("127.0.0.1"))) == "127.0.0.1"


class _FakeReq:
    def __init__(self, headers, client):
        self.headers = headers
        self.client = client


class _Client:
    def __init__(self, host):
        self.host = host
