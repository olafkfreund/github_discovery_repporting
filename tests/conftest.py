from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Override DATABASE_URL before any backend module is imported so that
# backend.config.settings picks up the in-memory SQLite URL.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", "")

# Now it is safe to import backend modules.
# Import all models so that Base.metadata is fully populated before we call
# create_all.  The __init__.py re-exports every mapped class, which triggers
# the mapper registry as a side-effect of the import.
import backend.models  # noqa: E402, F401
from backend.database import get_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.base import Base  # noqa: E402

# ---------------------------------------------------------------------------
# SQLite / aiosqlite compatibility shim
# ---------------------------------------------------------------------------
# SQLAlchemy's postgresql.UUID type renders as CHAR(32) on SQLite when
# native_enum and native_uuid processing are disabled, which is what we need
# for an in-memory test database.  We patch the dialect after engine creation
# via connect_args and engine execution options rather than monkey-patching
# any dialect internals.
#
# Enums that are stored as VARCHAR on PostgreSQL are rendered as TEXT on
# SQLite automatically by SQLAlchemy, so no extra work is required for those.

_TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create an in-memory SQLite async engine and build the schema.

    Each test function gets a fresh engine so schemas never leak between tests.
    The ``native_uuid=False`` option on the aiosqlite dialect makes SQLAlchemy
    render ``UUID`` columns as ``CHAR(32)`` which SQLite accepts without error.
    """
    async_engine = create_async_engine(
        _TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Patch the dialect so that postgresql.UUID columns are treated as CHAR
    # (native_uuid=False) rather than the postgresql-specific UUID type.
    async_engine.dialect.native_uuid = False  # type: ignore[attr-defined]

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_engine

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await async_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async session that is always rolled back.

    Using rollback instead of drop-all keeps each test isolated without
    rebuilding the schema for every test.
    """
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Return an httpx.AsyncClient wired to the FastAPI app.

    The ``get_db`` dependency is overridden to yield the test session so that
    every request in a test touches the same in-memory SQLite database as the
    test assertions.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    # Restore the real dependency so other test modules start clean.
    app.dependency_overrides.pop(get_db, None)
