"""HTTP entrypoint for the affärssystemet app (C26 run.py).

Binds uvicorn to 0.0.0.0:$PORT (no reload) so the hosting layer
(infra/vm106 repo-visibility-hosting, web-app-hosting skill) can point its
``exec: run.py`` at a port injected via the environment.

Usage:
    PORT=8199 python run.py

The small helper functions exist so the run-wiring is testable without
actually booting uvicorn (the app-appcore test imports this module).
"""

import os
from typing import Any


def resolve_port(env: dict[str, str] | None = None) -> int:
    """Return the port from ``$PORT``, raising if it is missing or invalid.

    The hosting layer injects ``PORT``; there is no default so a mis-configured
    deploy fails fast instead of silently serving on the wrong port.
    """
    env = os.environ if env is None else env
    raw = env.get("PORT")
    if not raw:
        raise RuntimeError(
            "PORT environment variable is required (set PORT=<port> before "
            "starting). Refusing to guess a default port."
        )
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"PORT must be an integer, got {raw!r}") from exc
    if not (0 < port < 65536):
        raise RuntimeError(f"PORT out of range (1..65535), got {port}")
    return port


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

    from app.main import create_app

    kwargs = build_uvicorn_kwargs()
    uvicorn.run(create_app(), **kwargs)


if __name__ == "__main__":
    main()
