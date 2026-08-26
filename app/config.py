"""Minimal env config shim (PLACEHOLDER — see note).

NOTE (650.1 seat): this file exists ONLY so ``app.database`` (the C2 init_db hookup
in THIS module's scope) can resolve DATABASE_URL during model verification. It is a
thin placeholder; the full ``app-db-config`` module (hard-fail SECRET_KEY per I6,
etc.) is a separate card that must SUPERSEDE this file at integration. It is not part
of the 650.1 deliverable contract and must not be treated as final.
"""

import os

_DATABASE_URL_DEFAULT = os.environ.get("AFFAR_DATABASE_URL", "sqlite:///./affar.db")

# Read at import time — tests override via env before importing app.database.
DATABASE_URL: str = _DATABASE_URL_DEFAULT
