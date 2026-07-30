"""
Database engine/session setup.

Reads DATABASE_URL from the environment. In production this should be
a Postgres URL (e.g. postgresql://user:pass@host:5432/infraos); for
local development or running the test suite without a real Postgres
instance, it falls back to a SQLite file (or in-memory for tests),
which SQLAlchemy handles identically at the ORM layer -- the schema
and queries in db_models.py / store.py don't change either way.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.environ.get("INFRAOS_DATABASE_URL", "sqlite:///./infraos.db")

if DATABASE_URL == "sqlite:///:memory:":
    # In-memory SQLite is per-connection by default, which would lose
    # data between separate get_session() calls (the test suite's use
    # case) -- StaticPool keeps a single shared connection alive so the
    # same in-memory database persists for the process lifetime.
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
else:
    _connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

Base = declarative_base()


def init_db() -> None:
    """Creates all tables if they don't exist yet. Safe to call on
    every startup -- a real deployment would use Alembic migrations
    instead, but this is enough to get the MVP running against a real
    Postgres instance without a separate migration step."""
    from app import db_models  # noqa: F401 -- ensures models are registered on Base
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
