"""
Database engine and session management.

We use SQLModel (SQLAlchemy + Pydantic). For local development the default is a
SQLite file, which needs zero setup. For production, point DATABASE_URL at
PostgreSQL and nothing else changes.
"""
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

# SQLite needs a special flag when used with a multi-threaded server like
# uvicorn; Postgres does not. We detect which one we're on and adjust.
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.sqlalchemy_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Create tables for local (SQLite) development only.

    In production (Postgres), the schema is owned by Alembic migrations, so we
    do NOT auto-create here — that's what caused the "missing column" problem
    when models changed. Run `alembic upgrade head` to apply migrations instead.
    """
    # Importing models here ensures they are registered on SQLModel.metadata
    # before we create the tables.
    from . import models  # noqa: F401

    if settings.is_sqlite:
        SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency that yields a database session per request."""
    with Session(engine) as session:
        yield session
