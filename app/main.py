"""Application factory + router wiring (contract C3, app-appcore).

    create_app() -> FastAPI    # registers ROUTES; on startup runs
                               # init_db() then seed_if_empty(); adds CORS
                               # for the SPA (dev).
    ROUTES: list[APIRouter]    # ordered router list inspected by the gate.

Only the routers that exist on the board at this task are registered. New
routers (tracking delivered by a later card) are added here by appending to
``ROUTES`` — the factory iterates the list, so wiring a new module is a
one-line change.
"""

from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.config as _cfg
from app.database import get_session_cm, init_db
from app.seed import seed_if_empty

# Ordered router list (C3) — inspected by the gate. Append new routers here.
ROUTES: list[APIRouter] = []

# Auth (C6) and catalog (C8) land before the remaining order/invoice/payment/
# buy-side/tracking routers (later cards). Append new routers here.
from app.routers import auth as _auth_router  # noqa: E402
from app.routers import items as _items_router  # noqa: E402
from app.routers import orders as _orders_router  # noqa: E402
from app.routers import invoices as _invoices_router  # noqa: E402
from app.routers import payments as _payments_router  # noqa: E402
from app.routers import purchase as _purchase_router  # noqa: E402
from app.routers import suppliers as _suppliers_router  # noqa: E402
from app.routers import tracking as _tracking_router  # noqa: E402

ROUTES.append(_auth_router.router)
ROUTES.append(_items_router.router)
ROUTES.append(_orders_router.router)
ROUTES.append(_invoices_router.router)
ROUTES.append(_payments_router.router)
ROUTES.append(_purchase_router.router)
ROUTES.append(_suppliers_router.router)
ROUTES.append(_tracking_router.router)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> Iterator[None]:
    """On startup: create tables, then seed the demo dataset if empty."""
    init_db()
    with get_session_cm() as db:
        seed_if_empty(db)
    yield


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="Affärssystemet API",
        version="2.6.0",
        description="Fullstack ERP (order->faktura->betalning + tracking + inköp).",
        lifespan=_lifespan,
    )

    # CORS for the SPA (dev, per C3). Origins are read from app.config when
    # the app-db-config card lands; until then a permissive dev default keeps
    # the local frontend reachable. Not hardened-secret territory — config is
    # read at runtime, never hardcoded.
    origins = getattr(_cfg, "CORS_ORIGINS", None) or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in ROUTES:
        app.include_router(router)

    return app
