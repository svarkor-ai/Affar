"""Shared fixtures for MC 650.3 (app-auth) verification tests.

The real app config (C1) lives in the app-db-config card (T2) and hard-fails
on a missing/short SECRET_KEY (I6). That card is NOT yet on the board when this
test runs, and the 650.1 placeholder config shim only carries DATABASE_URL.
These fixtures therefore inject the C1-shaped values (SECRET_KEY, JWT_ALGORITHM,
ACCESS_TOKEN_EXPIRE_MINUTES) onto the ``app.config`` module namespace before
``app.auth`` / ``app.database`` import them, mirroring exactly what the T2
config module will provide at integration. A deliberately-weak *test* secret is
used — never a production value.
"""

import os
import tempfile

# Point the database at a temp FILE sqlite (not :memory:). The FastAPI router
# opens sessions on the TestClient's thread; with an in-memory URL and the
# default per-thread pool each thread would get its own empty copy. A file
# sqlite is visible to all threads/connections.
_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["AFFAR_DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"

# --- Inject the C1 config attributes the auth module reads at import time ---
import app.config as _cfg  # noqa: E402

_cfg.SECRET_KEY = "test-secret-not-for-prod-0123456789abcdef"  # test-only
_cfg.JWT_ALGORITHM = "HS256"
_cfg.ACCESS_TOKEN_EXPIRE_MINUTES = 1  # keep short for expiry checks

# ---------------------------------------------------------------------------
# Per-test clean database
# ---------------------------------------------------------------------------
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    """Reset the in-memory schema before every test.

    The in-memory sqlite persists for the whole pytest process, so without a
    reset a second test that seeds the same username hits the UNIQUE
    constraint. drop_all + init_db gives each test a clean User table.
    """
    from app.database import drop_all, init_db

    drop_all()
    init_db()
    yield
