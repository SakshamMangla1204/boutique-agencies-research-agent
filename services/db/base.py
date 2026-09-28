"""SQLAlchemy declarative base for the AI agency/job research agent."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""

    pass
