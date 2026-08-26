"""Database engine, session, and init hookup (contract C2).

Reused near-verbatim from bibliotek src/database.py (C-C): lazy engine, WAL,
get_session/get_session_cm/init_db. The only change from the reuse source is the
DATABASE_URL source (app.config) and the models import (app.models).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

# Lazy import so that tests can override DATABASE_URL before the engine is built.
from app.config import DATABASE_URL  # noqa: E402
from app.models import Base

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_engine = None  # lazily created


def resolve_db_path() -> Path:
    """Resolve DATABASE_URL to the on-disk sqlite file Path."""
    if not DATABASE_URL.startswith("sqlite"):
        raise RuntimeError(
            f"Unsupported database URL scheme: {DATABASE_URL!r}. "
            "Affärssystemet requires SQLite."
        )

    db_path = DATABASE_URL.replace("sqlite:///", "")
    db_file = Path(db_path)
    if not db_file.is_absolute():
        db_file = Path(__file__).resolve().parent.parent / db_file

    db_file.parent.mkdir(parents=True, exist_ok=True)
    return db_file


def get_engine():
    """Return a shared SQLAlchemy engine (SQLite with WAL mode)."""
    global _engine
    if _engine is None:
        resolve_db_path()  # side effect: validates scheme + creates parent dir
        db_path = DATABASE_URL.replace("sqlite:///", "")

        connect_args = {}
        if db_path.startswith(":memory:"):
            connect_args = {"check_same_thread": False}

        _engine = create_engine(
            DATABASE_URL,
            connect_args=connect_args,
            pool_pre_ping=True,
            echo=False,
        )

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _conn_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")  # 64 MB
            cursor.close()

    return _engine


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------


@contextmanager
def get_session_cm() -> Iterator[Session]:
    """Context-manager version of get_session (manual usage / startup seed)."""
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session():
    """FastAPI dependency: yields a SQLAlchemy session."""
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create all tables defined in app/models (C2 hookup)."""
    Base.metadata.create_all(get_engine())


def drop_all() -> None:
    """Drop all tables (dev / seed only)."""
    Base.metadata.drop_all(get_engine())
