"""Tests for MC 702.1 (run.py self-provisioning): PORT-fallback + secret key.

Contract additions (per task 702.1 / gunilla deploy-prep blockers B1+B2):
    run.resolve_port(env)          -> DEFAULT_PORT (8110) when $PORT missing
    run.DEFAULT_PORT               == 8110 (hosting.yaml manifest port)
    run.state_key_path(env)        -> path under $STATE_DIRECTORY (or a local
                                     fallback) holding the persistent secret
    run.provision_secret(env)      -> reads $AFFAR_SECRET_KEY if set,
                                     else loads/generates a strong key in the
                                     StateDirectory key file (0600) and
                                     returns it; on first use it WRITES a fresh
                                     key file, on later use it READS the same
                                     file (persistence across restarts).
    run.main() injects os.environ["AFFAR_SECRET_KEY"] BEFORE importing app.main
"""

import importlib.util
import os
import stat

import pytest

# Import the module under a name that has no side effects (no top-level
# uvicorn.run). Mirrors the existing test_run_py_reads_PORT_env pattern.
_spec = importlib.util.spec_from_file_location(
    "affar_run_self",
    os.path.join(os.path.dirname(__file__), "..", "run.py"),
)
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)


def _env(**overrides):
    base = {k: v for k, v in os.environ.items() if v is not None}
    base.update(overrides)
    return base


def test_port_fallback_defaults_to_8110():
    env = _env()
    env.pop("PORT", None)
    assert run.DEFAULT_PORT == 8110
    assert run.resolve_port(env) == 8110


def test_port_explicit_still_respected():
    env = _env(PORT="8199")
    assert run.resolve_port(env) == 8199


def test_state_key_path_under_state_directory(tmp_path):
    env = _env(STATE_DIRECTORY=str(tmp_path))
    p = run.state_key_path(env)
    assert p == os.path.join(str(tmp_path), "secret.key")
    # path is absolute, inside STATE_DIRECTORY
    assert str(tmp_path) in p


def test_provision_generates_and_persists(tmp_path):
    env = _env()
    env.pop("AFFAR_SECRET_KEY", None)
    env["STATE_DIRECTORY"] = str(tmp_path)
    # First call: no AFFAR_SECRET_KEY, no existing key file -> generate + write.
    key1 = run.provision_secret(env)
    assert key1
    assert len(key1) >= 24
    # Key file created with owner-only 0600 perms (secret material).
    key_path = run.state_key_path(env)
    assert os.path.exists(key_path)
    mode = stat.S_IMODE(os.stat(key_path).st_mode)
    assert mode == 0o600, f"key file mode={oct(mode)}, want 0600"
    # Persistence: second call reads the same key back (restart survives).
    key2 = run.provision_secret(env)
    assert key2 == key1, "secret must persist across restarts"


def test_provision_respects_operator_explicit_key(tmp_path):
    env = _env(AFFAR_SECRET_KEY="operator-provided-strong-key-0123456789ab")
    env["STATE_DIRECTORY"] = str(tmp_path)
    key = run.provision_secret(env)
    assert key == "operator-provided-strong-key-0123456789ab"
    # Operator key must not be written to a key file.
    assert not os.path.exists(run.state_key_path(env))


def test_provision_key_passes_config_validation(tmp_path):
    from app.config import validate_secret_key
    env = _env(STATE_DIRECTORY=str(tmp_path))
    env.pop("AFFAR_SECRET_KEY", None)
    key = run.provision_secret(env)
    assert validate_secret_key(key) == key
