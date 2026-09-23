"""Idempotent startup migration for pre-1175 SQLite databases (MC 1323.1).

The schema (I1) deliberately has no migration framework (no Alembic). But
Base.metadata.create_all() does NOT add columns to existing tables, so a live
DB created by the 2026-09-06 build crashes on startup against current master
with "no such column: users.is_active". This module adds a small, generic,
idempotent helper: discover missing columns via PRAGMA table_info and issue
plain "ALTER TABLE ... ADD COLUMN" for each. SQLite only (the app requires
SQLite — app.database.resolve_db_path enforces it).

Wired from app.database.init_db(), i.e. it runs on every startup AFTER
create_all and BEFORE seed_if_empty (main.py's lifespan order).
"""

from sqlalchemy import text

from app.models import Base

# Columns current models expect that a pre-1175 (2026-09-06 build) DB lacks.
# (table, column, DDL type clause) — kept in sync with app/models/*.py.
STARTUP_MIGRATIONS: list[tuple[str, str, str]] = [
    ("users", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("customers", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("suppliers", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("payments", "cancels_payment_id", "INTEGER"),
]


def _existing_columns(conn, table: str) -> set[str]:
    """Column names of `table` via PRAGMA table_info (empty if table absent)."""
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def ensure_columns(migrations: list[tuple[str, str, str]]) -> int:
    """Idempotently add any missing (table, column, ddl) triple. Returns count."""
    from app.database import get_engine

    added = 0
    with get_engine().connect() as conn:
        for table, column, ddl in migrations:
            if not _existing_columns(conn, table):
                continue  # table does not exist — create_all owns it
            if column in _existing_columns(conn, table):
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            added += 1
        conn.commit()
    return added


def run_startup_migrations() -> int:
    """Run the known startup migrations. Called from init_db() after create_all."""
    return ensure_columns(STARTUP_MIGRATIONS)
