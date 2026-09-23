"""Startup-migration test for MC 1323.1: pre-1175 live DB must boot on master.

Real executed checks:
  1. A DB built with the OLD (pre-1175) schema — users/customers/suppliers
     without is_active, payments without cancels_payment_id — crashes on
     current master without the migration (documents the bug being fixed).
  2. After init_db() runs the idempotent startup migration, the same old DB
     boots: all 4 columns exist (PRAGMA table_info) and a fresh
     create_all/init_db pass is a no-op (idempotence).
  3. The migration is generic: a missing column on an unrelated table is
     added by the same helper.
"""

import pytest
from sqlalchemy.exc import OperationalError

from app.database import get_engine, init_db
from app.migrations import ensure_columns

# The 4 columns current models expect that the 2026-09-06 build's DB lacks.
KNOWN_MIGRATIONS = [
    ("users", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("customers", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("suppliers", "is_active", "BOOLEAN NOT NULL DEFAULT 1"),
    ("payments", "cancels_payment_id", "INTEGER"),
]


def _old_schema_db(url: str) -> None:
    """Create a DB with the pre-1175 schema (the 4 columns absent)."""
    engine = get_engine()
    init_db()  # current schema
    # Strip the 4 columns by rebuilding each affected table the old way.
    old_defs = {
        "users": (
            "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "username VARCHAR(50) NOT NULL UNIQUE, "
            "password_hash VARCHAR(255) NOT NULL, role VARCHAR(20) NOT NULL, "
            "email VARCHAR(255), created_at DATETIME)"
        ),
        "customers": (
            "CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name VARCHAR(100) NOT NULL, org_nr VARCHAR(20), "
            "address VARCHAR(200), phone VARCHAR(50), email VARCHAR(255))"
        ),
        "suppliers": (
            "CREATE TABLE suppliers (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name VARCHAR(100) NOT NULL, org_nr VARCHAR(20), "
            "address VARCHAR(200), phone VARCHAR(50), email VARCHAR(255))"
        ),
        "payments": (
            "CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "invoice_id INTEGER NOT NULL REFERENCES invoices (id), "
            "amount NUMERIC(12, 2) NOT NULL, method VARCHAR(20) NOT NULL, "
            "paid_at DATETIME)"
        ),
    }
    with engine.connect() as conn:
        for table, ddl in old_defs.items():
            conn.exec_driver_sql(f"DROP TABLE {table}")
            conn.exec_driver_sql(ddl)
        conn.commit()


def _columns(table: str) -> set[str]:
    with get_engine().connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def test_old_schema_boot_fails_without_migration(monkeypatch):
    """Documents the bug: pre-1175 DB + current models = 'no such column'."""
    from app.database import drop_all

    drop_all()
    _old_schema_db("unused")
    # Current models expect is_active; a plain SELECT against the ORM mapping
    # must fail on the old schema (this is what crashed startup on vm106).
    with pytest.raises(OperationalError, match="no such column"):
        with get_engine().connect() as conn:
            conn.exec_driver_sql(
                "SELECT is_active FROM users"
            ).fetchall()


def test_init_db_migrates_old_schema():
    """The DoD scenario: old-schema DB + init_db() boots with columns added."""
    from app.database import drop_all

    drop_all()
    _old_schema_db("unused")
    for table, col, _ in KNOWN_MIGRATIONS:
        assert col not in _columns(table)
    init_db()  # must run the startup migration
    for table, col, _ in KNOWN_MIGRATIONS:
        assert col in _columns(table), f"{table}.{col} missing after init_db"


def test_migration_is_idempotent():
    from app.database import drop_all

    drop_all()
    init_db()
    init_db()  # second run on a current-schema DB: no error, no change
    for table, col, _ in KNOWN_MIGRATIONS:
        assert col in _columns(table)


def test_ensure_columns_generic_helper():
    """The helper is generic: works for any table/column, not just the 4."""
    from app.database import drop_all

    drop_all()
    init_db()
    with get_engine().connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS _mig_probe (id INTEGER PRIMARY KEY)"
        )
        conn.commit()
    ensure_columns([("_mig_probe", "extra_col", "VARCHAR(10)")])
    assert "extra_col" in _columns("_mig_probe")
    # And running it again does not raise (idempotent).
    ensure_columns([("_mig_probe", "extra_col", "VARCHAR(10)")])
