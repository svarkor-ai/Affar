# Affär — Architecture

## Purpose

Affär is a fullstack ERP demo (Swedish UI): orders with international tracking,
invoices, payments, customers, items, suppliers and purchase flow, built against
ERPNext as a model and hosted on the vm106 portfolio host. FastAPI backend +
SQLAlchemy/SQLite, React/Vite SPA served by the same backend. PoC-demo intent:
the demo write-guard, not production hardening, is the deliberate simplification.

## Tree map

```
app/                  FastAPI backend
  routers/            HTTP layer: auth, items, orders, invoices, payments,
                      customers, purchase, suppliers, tracking, reports, admin_users
  services/           business logic (invoicing, payments, purchase, reports,
                      *_edit re-open/edit flows, catalog, tracking, admin_users)
  models/             SQLAlchemy models (user, item, order, invoice/finance,
                      payment, customer, supplier, purchase, tracking, base)
  schemas/            Pydantic schemas per domain (+ money.py decimal handling)
  auth.py             bcrypt hashing, HS256 JWT, require_role dependency
  demo_guard.py       DemoWriteGuard middleware (write gating for the demo)
  migrations.py       idempotent startup ALTER TABLE migrations (no Alembic)
  database.py         engine/session, SQLite-only path resolution, init_db
  config.py           env config, hard-fails without AFFAR_SECRET_KEY (I6)
  main.py             create_app() factory, ROUTES list, SPA mount of dist/
  seed.py             seed_if_empty() demo data on startup
src/                  React/Vite SPA
  views/              one view per domain (Dashboard, Orders, Invoices, Payments,
                      Customers, Suppliers, Items, Purchase, Track, AdminUsers, Login)
  components/         Layout, DataTable, Money, StatusBadge
  api.js              typed fetch client, prefix-safe BASE ("api"), Bearer tokens
  auth.context.jsx    login/token/role React context
  App.jsx, main.jsx, styles.css
dist/                 built Vite bundle — the deployed artifact (served by backend)
tests/                pytest suite (backend contract, run.py wiring, migrations)
run.py                entrypoint: port resolution, secret self-provision, uvicorn boot
mock-server.mjs       dev-only mock API + static server (NOT part of the deliverable)
hosting.yaml          vm106 mirror spec (service, port 8110, cachebust)
index.html, vite.config.js, package.json, package-lock.json   frontend build inputs
requirements.txt      exact backend pins
LEDGER.md             the one project ledger
affar.db              local dev SQLite (repo copy; live DB lives in StateDirectory)
```

## Entrypoints and port binding

- `run.py` is the only production entrypoint (`exec: run.py` in hosting.yaml).
  It resolves `$PORT` with fallback to `DEFAULT_PORT = 8110` (invalid PORT fails
  fast), self-provisions `AFFAR_SECRET_KEY` into the systemd StateDirectory
  (`$STATE_DIRECTORY/secret.key`, 0600; local fallback `~/.local/state/affar`),
  defaults `AFFAR_DATABASE_URL` to the StateDirectory SQLite file, then boots
  uvicorn on `0.0.0.0:$PORT` with `create_app()`.
- `mock-server.mjs` is a dev-only aid (port 4173 default) to vision-check the UI;
  never deployed.
- `hosting.yaml` declares `type: service`, `root: apps/affar`, `port: 8110`,
  mirror excludes that keep `run.py`, `app/**`, `dist/**`, `requirements.txt`
  served and drop dev cruft; `cachebust: all`.

## Dependencies

- Backend (`requirements.txt`, exact pins only — vm106 build gate rejects ranges):
  fastapi==0.141.1, uvicorn==0.52.4, sqlalchemy==2.0.52, pydantic==2.13.4,
  bcrypt==5.0.0, python-jose==3.5.0.
- Frontend (`package.json`): react/react-dom ^18.3.1; devDeps vite ^5.4.0,
  @vitejs/plugin-react ^4.3.1. Build via `vite build` into `dist/`.

## Data store

SQLite (`affar.db`). In production the DB lives in the systemd StateDirectory
(never the repo tree — the vm106 unit runs ProtectSystem=strict); the repo-root
`affar.db` is a local-dev artifact. No migration framework: `app/migrations.py`
runs idempotent `ALTER TABLE ... ADD COLUMN` statements (discovered via PRAGMA
table_info) on every startup, after `create_all()` and before `seed_if_empty()`.
Money is stored/handled as decimals with comma-decimal normalization (schemas +
tests `test_comma_decimals_1182_6`).

## Auth model

bcrypt password hashing + HS256 JWTs (`python-jose`), 24h token expiry.
`app/auth.py` declares the closed role set — `admin, sales, finance,
procurement, customer` — mirrored exactly by `app/models/user.py`. Every
business route is gated with `require_role(...)`; `get_current_user` (no role
check) backs only the public `GET /api/auth/me`. `config.py` hard-fails at
import without a strong `AFFAR_SECRET_KEY` — there is no fallback secret.
`demo_guard.py` adds a write-guard middleware for the demo deployment.

## Live deployment fact

The app is served at **https://sibbamala.com/affar/** via the vm106 hosting
mirror. The deployed artifact is the built `dist/` bundle (assets
`index-CsGtcfR4.js`, `index-D755bMaq.css` at master d8b0bd8); the backend serves
the SPA from `dist/` (`/assets` mount + SPA catch-all) under the `/affar/`
prefix. `src/api.js` uses a relative `api` base so requests stay inside the
`/affar/` prefix behind the reverse proxy. hosting.yaml sets `cachebust: all`;
cachebust `?v=` query params are appended to asset URLs by the mirror layer.
