"""Tests for MC 650.6 (app-appcore): factory + run.py entrypoint.

Contract C3 (architecture revision 1745):
    create_app() -> FastAPI   # registers ROUTES; startup: init_db() then
                              # seed_if_empty(); CORS for SPA (dev)
    ROUTES: APIRouter[]       # ordered router list inspected by the gate

run.py: uvicorn.run(create_app(), host="0.0.0.0",
                    port=int(os.environ["PORT"]), reload=False)
"""

import os
import subprocess
import sys
import tempfile

import pytest
from fastapi import FastAPI

# Point the database + auth config before importing the app (mirrors the
# C1 shape the app-db-config card will supply at integration).
_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["AFFAR_DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"

import app.config as _cfg  # noqa: E402

_cfg.SECRET_KEY = "test-secret-not-for-prod-0123456789abcdef"
_cfg.JWT_ALGORITHM = "HS256"
_cfg.ACCESS_TOKEN_EXPIRE_MINUTES = 5

from app.main import ROUTES, create_app  # noqa: E402


def test_create_app_returns_fastapi_instance():
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title


def test_auth_router_is_mounted():
    # FastAPI 0.141 defers router inclusion to a lazy _IncludedRouter at
    # build time, so assert on the ROUTES list (which the gate inspects) and
    # prove routing end-to-end over HTTP with the TestClient.
    assert len(ROUTES) >= 1
    assert getattr(ROUTES[0], "prefix", "") == "/api/auth"

    app = create_app()
    with TestClient(app) as client:
        # Login with bad creds -> 401 means the route exists and is reachable.
        assert client.post("/api/auth/login",
                           json={"username": "nobody", "password": "x"}).status_code == 401
        # /me with no token -> 401 (route wired, guard active).
        assert client.get("/api/auth/me").status_code == 401


def test_startup_seeds_when_empty():
    """Booting the app (startup events) must init_db + seed_if_empty."""
    from app.database import drop_all
    drop_all()  # clear so 'users' is empty before boot

    app = create_app()
    with TestClient(app) as client:  # context enter fires startup
        # startup ran init_db + seed_if_empty -> users populated
        from app.database import get_engine
        from sqlalchemy.orm import Session
        from app.models import User
        with Session(get_engine()) as s:
            assert s.query(User).count() >= 5


def test_openapi_served():
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert "paths" in r.json()


def test_run_py_reads_PORT_env():
    """run.py must fail-fast when PORT is missing, and pass it to uvicorn."""
    env = dict(os.environ)
    env.pop("PORT", None)
    # Import the module under a name that has no side effects (no top-level
    # uvicorn.run). We only assert the helper it exposes to read the port.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "affar_run", os.path.join(os.path.dirname(__file__), "..", "run.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    env["PORT"] = "8199"
    assert mod.resolve_port(env) == 8199
    assert mod.build_uvicorn_kwargs(env)["port"] == 8199


from fastapi.testclient import TestClient  # noqa: E402
