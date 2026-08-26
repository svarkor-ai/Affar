"""Shared fixtures for MC 650.3 (app-auth) verification tests.

The real app config (C1, app/config.py) was delivered by MC 691.1 (R1) and
reads everything from the environment, hard-failing at import (I6) when no
SECRET_KEY is present. These fixtures therefore set AFFAR_SECRET_KEY in the
environment BEFORE ``app.config`` is imported, exactly as an operator would
before starting the app. A deliberately-strong *test* secret is used in the
env — never a production value.
"""

import os
import tempfile

# Provide a valid SECRET_KEY via the env BEFORE any app module imports config
# (C1 hard-fails at import when the env key is missing, short or insecure).
os.environ["AFFAR_SECRET_KEY"] = "test-secret-not-for-prod-0123456789abcdef"

# Point the database at a temp FILE sqlite (not :memory:). The FastAPI router
# opens sessions on the TestClient's thread; with an in-memory URL and the
# default per-thread pool each thread would get its own empty copy. A file
# sqlite is visible to all threads/connections.
_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["AFFAR_DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"

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
