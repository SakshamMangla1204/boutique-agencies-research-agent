"""PostgreSQL session/engine management with a graceful optional-DB fallback.

Set `DATABASE_URL` to enable persistence.  When it is missing (or the database
is unreachable), `is_db_enabled()` returns False and the pipeline continues in
Sheets-only mode instead of crashing.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

_DB_STATE: dict = {"checked": False, "engine": None, "enabled": False, "reason": ""}

# Common tracker/query noise stripped from job URLs before hashing.
_URL_NOISE_PARAMS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "referrer", "src", "trackingid", "trk",
    "gh_src", "lever-source", "lever-origin",
)


def get_database_url() -> str:
    """Return the configured DATABASE_URL (empty string when unset)."""
    return os.getenv("DATABASE_URL", "").strip()


def _create_engine(url: str):
    from sqlalchemy import create_engine

    # Accept provider URLs verbatim, but default to the psycopg2 driver.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )


def init_db(force: bool = False) -> bool:
    """Create tables if a database is configured and reachable.

    Returns True when the database is ready for use.  Never raises: a missing
    or unreachable database simply disables persistence.
    """
    if _DB_STATE["checked"] and not force:
        return _DB_STATE["enabled"]

    _DB_STATE["checked"] = True
    url = get_database_url()

    if not url:
        _DB_STATE["engine"] = None
        _DB_STATE["enabled"] = False
        _DB_STATE["reason"] = "DATABASE_URL is not set"
        return False

    try:
        from services.db.base import Base
        from services.db import models  # noqa: F401  (register tables)

        engine = _create_engine(url)
        Base.metadata.create_all(engine)

        _DB_STATE["engine"] = engine
        _DB_STATE["enabled"] = True
        _DB_STATE["reason"] = ""
        return True
    except Exception as exc:  # pragma: no cover - depends on environment
        _DB_STATE["engine"] = None
        _DB_STATE["enabled"] = False
        _DB_STATE["reason"] = f"{type(exc).__name__}: {exc}"
        return False


def is_db_enabled() -> bool:
    """True when a working database session can be obtained."""
    return init_db()


def db_status() -> str:
    """Human-readable status used in startup logging."""
    if is_db_enabled():
        return "enabled"

    reason = _DB_STATE.get("reason") or "not configured"
    return f"disabled ({reason})"


def get_engine():
    if not init_db():
        return None

    return _DB_STATE["engine"]


def get_session():
    """Return a new SQLAlchemy Session, or None when the DB is unavailable."""
    engine = get_engine()

    if engine is None:
        return None

    from sqlalchemy.orm import Session

    return Session(engine)
