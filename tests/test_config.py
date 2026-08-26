"""Tests for C1-config (MC 691.1 R1): app/config.py SECRET_KEY hard-fail + JWT.

Contract C1 (architecture rev 1745):
    app/config.py — env config, hard-fail. Raises RuntimeError at import
    (validate_secret_key, I6) when SECRET_KEY is unset / too short /
    known-insecure. No fallback secret ever. Exposes:
        DATABASE_URL              (env AFFAR_DATABASE_URL, default sqlite)
        SECRET_KEY                (env AFFAR_SECRET_KEY, hard-fail)
        JWT_ALGORITHM = "HS256"
        ACCESS_TOKEN_EXPIRE_MINUTES: int

The happy-path assertions run against the real app.config in-process. The
I6 "refuses to start" behaviour is proven in a fresh subprocess so that a
poisoned/absent secret can actually be observed at import time.
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_import_subprocess(extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    """Import app.config in a fresh interpreter; return the result."""
    env = {k: v for k, v in os.environ.items() if k != "AFFAR_SECRET_KEY"}
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# C1 contract surface (in-process, env provides a valid test secret via conftest)
# ---------------------------------------------------------------------------


def test_config_exposes_contract_names():
    import app.config as _cfg

    assert isinstance(_cfg.DATABASE_URL, str)
    assert _cfg.JWT_ALGORITHM == "HS256"
    assert isinstance(_cfg.ACCESS_TOKEN_EXPIRE_MINUTES, int)
    assert _cfg.ACCESS_TOKEN_EXPIRE_MINUTES > 0
    # A real SECRET_KEY must be present (not a placeholder / fallback).
    assert isinstance(_cfg.SECRET_KEY, str)
    assert len(_cfg.SECRET_KEY) >= 24


def test_validate_secret_key_rejects_bad_values():
    from app.config import validate_secret_key

    for bad in (None, "", "short", "secret", "change-me-in-production"):
        with pytest.raises(RuntimeError):
            validate_secret_key(bad)


def test_validate_secret_key_accepts_strong_value():
    from app.config import validate_secret_key

    valid = "0123456789abcdefghijklmnop"  # 24 chars
    assert validate_secret_key(valid) == valid


# ---------------------------------------------------------------------------
# I6 — the app refuses to start without a valid key (fresh subprocess)
# ---------------------------------------------------------------------------


def test_missing_secret_fails_at_import():
    """No AFFAR_SECRET_KEY -> RuntimeError at import (I6 hard-fail)."""
    result = _run_import_subprocess({})
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_short_secret_fails_at_import():
    """Too-short AFFAR_SECRET_KEY -> RuntimeError at import (I6 hard-fail)."""
    result = _run_import_subprocess({"AFFAR_SECRET_KEY": "short"})
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_known_insecure_secret_fails_at_import():
    """Known-insecure AFFAR_SECRET_KEY -> RuntimeError at import (I6)."""
    result = _run_import_subprocess({"AFFAR_SECRET_KEY": "change-me-in-production"})
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_valid_secret_imports_cleanly():
    """A strong AFFAR_SECRET_KEY -> clean import, no crash."""
    result = _run_import_subprocess({"AFFAR_SECRET_KEY": "0123456789abcdefghijklmnop"})
    assert result.returncode == 0, result.stderr
