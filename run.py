"""
Provider: teddy, MC 702.1 (R1 — run.py PORT-fallback + självprovisionerad
AFFAR_SECRET_KEY StateDirectory). Supersedes: MC 650.6 run.py that raised
when PORT was missing and left secret provisioning to the operator.

Resolves gunilla's deploy-prep blockers (MC 697.2):
  B1 PORT            -> resolve_port() now falls back to DEFAULT_PORT (8110)
                       instead of raising when $PORT is missing.
  B2 AFFAR_SECRET_KEY -> run.py self-provisions a strong key persisted in the
                       systemd StateDirectory ($STATE_DIRECTORY/secret.key,
                       0600) and injects it into the env BEFORE app.config is
                       imported, so the module never hard-crashes at import
                       and the key survives restarts WITHOUT being committed.

Usage:
    [PORT=8199] python run.py          # PORT optional, defaults to 8110
    [STATE_DIRECTORY=/var/lib/affar]   # systemd sets this; local fallback used otherwise

The small helper functions exist so the run-wiring is testable without
actually booting uvicorn (the app-appcore test imports this module).
"""

import os
import secrets
from typing import Any

# The manifest/hosting.yaml port for affar. Used as the fallback when $PORT is
# not injected (the vm106 service renderer does not pass PORT as arg/env).
DEFAULT_PORT = 8110

# Name of the key file inside the StateDirectory. systemd provides
# $STATE_DIRECTORY=/var/lib/<service> for units with StateDirectory=.
_SECRET_KEY_FILE = "secret.key"

# Local (non-systemd) state fallback so `python run.py` still works when there
# is no StateDirectory (kept under $HOME, never inside the repo tree).
_LOCAL_STATE_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "state", "affar"
)


def resolve_port(env: dict[str, str] | None = None) -> int:
    """Return the port from ``$PORT``, falling back to ``DEFAULT_PORT`` (8110).

    The hosting layer may inject ``PORT``; when it does not, the app still
    boots on the manifest port instead of failing (MC 702.1 PORT-fallback).
    An explicit but invalid PORT still fails fast.
    """
    env = os.environ if env is None else env
    raw = env.get("PORT")
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"PORT must be an integer, got {raw!r}") from exc
    if not (0 < port < 65536):
        raise RuntimeError(f"PORT out of range (1..65535), got {port}")
    return port


def state_key_path(env: dict[str, str] | None = None) -> str:
    """Return the persistent secret-key file path.

    Uses ``$STATE_DIRECTORY`` when set (systemd StateDirectory=), otherwise
    the local fallback under ``$HOME/.local/state/affar``.
    """
    env = os.environ if env is None else env
    base = env.get("STATE_DIRECTORY") or _LOCAL_STATE_DIR
    return os.path.join(base, _SECRET_KEY_FILE)


def provision_secret(env: dict[str, str] | None = None) -> str:
    """Return the JWT signing key, self-provisioning it if needed.

    Resolution order:
      1. An operator-set ``$AFFAR_SECRET_KEY`` wins (never overwritten, never
         written to disk here).
      2. Otherwise an existing StateDirectory key file is read (persistence
         across restarts).
      3. Otherwise a fresh strong key is generated and persisted to the
         StateDirectory key file with owner-only 0600 permissions.
    """
    env = os.environ if env is None else env
    explicit = env.get("AFFAR_SECRET_KEY")
    if explicit:
        return explicit

    key_path = state_key_path(env)
    if os.path.exists(key_path):
        with open(key_path, "r", encoding="utf-8") as fh:
            return fh.read().strip()

    # No existing key: generate a fresh one and persist it (0600), mirroring
    # how an operator would export AFFAR_SECRET_KEY.
    fresh = secrets.token_urlsafe(48)  # 64 chars, well above the 24-char floor
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(fresh + "\n")
    os.chmod(key_path, 0o600)  # explicit, guard against umask surprises
    return fresh


def build_uvicorn_kwargs(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Assemble the uvicorn.run() kwargs (host 0.0.0.0, port $PORT, no reload)."""
    return {
        "host": "0.0.0.0",
        "port": resolve_port(env),
        "reload": False,
        "log_level": "info",
    }


def main() -> None:
    """Boot the app. Executed only when this file is run directly."""
    import uvicorn

    # Self-provision AFFAR_SECRET_KEY and inject it BEFORE app.config is
    # imported (config.py hard-fails at import without it, I6). The key lives
    # in the StateDirectory and is never committed.
    os.environ["AFFAR_SECRET_KEY"] = provision_secret()

    from app.main import create_app

    kwargs = build_uvicorn_kwargs()
    uvicorn.run(create_app(), **kwargs)


if __name__ == "__main__":
    main()
