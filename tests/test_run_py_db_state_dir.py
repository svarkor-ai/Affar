"""Tests for MC 707.2 G1: run.py must point AFFAR_DATABASE_URL at the
StateDirectory so the app never writes sqlite files inside the (read-only
under vm106 ProtectSystem=strict) repo tree.

Contract additions (task 707.2, pattern: hotell server.py MC 1923):
    run.state_db_url(env)  -> sqlite:///<$STATE_DIRECTORY or local state>/affar.db
    run.main() injects os.environ["AFFAR_DATABASE_URL"] BEFORE importing
    app.config (which reads DATABASE_URL once at import).
    An operator-set AFFAR_DATABASE_URL wins and is never overwritten.
"""

import importlib.util
import os

# Import the module under test side-effect-free (no top-level uvicorn.run).
_spec = importlib.util.spec_from_file_location(
    "affar_run_db",
    os.path.join(os.path.dirname(__file__), "..", "run.py"),
)
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)


def _bare_env(**overrides):
    """Env WITHOUT AFFAR_* / STATE_DIRECTORY noise, plus overrides."""
    base = {
        k: v
        for k, v in os.environ.items()
        if v is not None
        and k not in {"STATE_DIRECTORY", "AFFAR_DATABASE_URL", "AFFAR_SECRET_KEY"}
    }
    base.update(overrides)
    return base


def test_state_db_url_under_state_directory(tmp_path):
    env = _bare_env(STATE_DIRECTORY=str(tmp_path))
    url = run.state_db_url(env)
    assert url == f"sqlite:///{tmp_path / 'affar.db'}"


def test_state_db_url_falls_back_to_local_state(tmp_path, monkeypatch):
    # _LOCAL_STATE_DIR is module-level (expanded at import), so assert the
    # fallback against it directly rather than against a monkeypatched $HOME.
    monkeypatch.delenv("STATE_DIRECTORY", raising=False)
    env = _bare_env()
    env.pop("STATE_DIRECTORY", None)
    url = run.state_db_url(env)
    assert url == f"sqlite:///{os.path.join(run._LOCAL_STATE_DIR, 'affar.db')}"
    assert not url.startswith("sqlite:///./"), "must never default to the repo-relative path"
    assert run._LOCAL_STATE_DIR not in os.getcwd(), "fallback must live outside the repo tree"


def test_ensure_state_db_dir_creates_parent(tmp_path):
    env = _bare_env(STATE_DIRECTORY=str(tmp_path / "fresh"))
    run.ensure_state_db_dir(env)
    assert (tmp_path / "fresh").is_dir()


def test_main_injects_db_url_before_app_import(tmp_path, monkeypatch):
    """main() must export AFFAR_DATABASE_URL (state-dir db) into os.environ
    BEFORE app.config is imported — simulate by checking env after the
    provisioning step, with uvicorn and the app import stubbed out."""
    import sys
    import types

    fake_uvicorn = types.ModuleType("uvicorn")
    calls = {}

    def _run(app, **kwargs):
        calls["env_db"] = os.environ.get("AFFAR_DATABASE_URL")
        calls["env_key"] = os.environ.get("AFFAR_SECRET_KEY")

    fake_uvicorn.run = _run
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    monkeypatch.setenv("STATE_DIRECTORY", str(tmp_path))
    monkeypatch.delenv("AFFAR_DATABASE_URL", raising=False)
    monkeypatch.delenv("AFFAR_SECRET_KEY", raising=False)

    run.main()

    assert calls["env_db"] == f"sqlite:///{tmp_path / 'affar.db'}"
    assert calls["env_key"], "secret key must still be self-provisioned (702.1)"


def test_main_respects_operator_database_url(tmp_path, monkeypatch):
    import sys
    import types

    fake_uvicorn = types.ModuleType("uvicorn")
    calls = {}
    fake_uvicorn.run = lambda app, **kw: calls.update(
        env_db=os.environ.get("AFFAR_DATABASE_URL")
    )
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    monkeypatch.setenv("STATE_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("AFFAR_DATABASE_URL", "sqlite:////srv/other/affar.db")

    run.main()
    assert calls["env_db"] == "sqlite:////srv/other/affar.db"
