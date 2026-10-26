"""Database engine + session wiring.

The bundled Postgres (see docker-compose.yml) is the system of record for
runs, samples, model results and the historised manual decisions. The live
flow still computes on in-memory DataFrames for the active run; every stage
write-through-persists to the DB so history survives container restarts.

`DATABASE_URL` is injected by compose
(`postgresql+psycopg://uc44:uc44@db:5432/uc44`). When it is absent — e.g. a
developer running `uvicorn` locally without Docker — we fall back to a SQLite
file so the app still boots. The ORM types are chosen to work on both
backends (`Uuid`, generic `JSON` with a JSONB variant on Postgres).
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .paths import BACKEND_DIR

# Default to a local SQLite file when no Postgres URL is configured. Compose
# always sets DATABASE_URL, so this only kicks in for bare local dev.
_DEFAULT_SQLITE = f"sqlite:///{BACKEND_DIR / 'uc44_local.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_SQLITE)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create tables if they do not exist (prototype-grade; no Alembic)."""
    # Import models so they are registered on Base.metadata before create_all.
    from ..models import orm  # noqa: F401

    # The correction-memory embedding column needs the pgvector extension to
    # exist before the table is created. No-op / skipped on SQLite (dev fallback).
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

    Base.metadata.create_all(bind=engine)

    # Additive column migrations (no Alembic): create_all never ALTERs an
    # existing table, so a column added to an already-created table must be
    # patched in here. Each step is idempotent (guarded by an inspector check)
    # and additive-only, so it is safe to run on every startup and on a DB with
    # real data (no `down -v` needed on the VM).
    _run_additive_migrations()

    # A run left in 'running' means the process died mid-analysis (its worker
    # thread is gone). Mark such runs failed so the UI shows them as
    # interruptible/retryable instead of spinning forever.
    with SessionLocal() as session:
        stale = session.query(orm.Run).filter(orm.Run.status == "running").all()
        for run in stale:
            run.status = "failed"
            run.stage = None
            run.error = "Unterbrochen durch Neustart"
        # Same for enrichment batches whose daemon thread died mid-run.
        stale_batches = (
            session.query(orm.EnrichmentBatch)
            .filter(orm.EnrichmentBatch.status == "running")
            .all()
        )
        for batch in stale_batches:
            batch.status = "failed"
            batch.error = "Unterbrochen durch Neustart"
        if stale or stale_batches:
            session.commit()


def _run_additive_migrations() -> None:
    """Idempotent, additive-only column patches for tables create_all already made.

    Kept deliberately tiny and dependency-free (no Alembic). Every step first
    checks the live schema via the inspector and only ADDs what is missing, so
    running it on every startup — including on the VM's populated Postgres — is a
    no-op once applied. Extend with further `_add_column_if_missing(...)` calls
    as the schema grows.
    """
    inspector = inspect(engine)
    if "warengruppe" in inspector.get_table_names():
        # Soft-delete flag; back-fill existing rows to active (TRUE / 1).
        default_true = "TRUE" if engine.dialect.name == "postgresql" else "1"
        _add_column_if_missing(
            inspector,
            table="warengruppe",
            column="aktiv",
            ddl_type=f"BOOLEAN NOT NULL DEFAULT {default_true}",
        )


def _add_column_if_missing(inspector, *, table: str, column: str, ddl_type: str) -> None:
    """ALTER TABLE ... ADD COLUMN, but only when the column is absent."""
    existing = {c["name"] for c in inspector.get_columns(table)}
    if column in existing:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def get_session():
    """FastAPI dependency / context helper yielding a scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
