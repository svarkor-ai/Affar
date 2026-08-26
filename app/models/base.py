"""Declarative base for the affärssystemet ORM aggregates."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base shared by every ORM aggregate in app/models.

    Invariant I1: the schema (these aggregates) is the single source of truth;
    routers and seed import from app.models, never re-declare columns.
    """
