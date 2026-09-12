"""Shared pytest fixtures for Phase 1 tests."""

import sys
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aos.api.main import create_app
from aos.db.engine import engine as app_engine
from aos.db.models import Base

# Python 3.14 on Windows: use SelectorEventLoop to avoid proactor None bug
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Separate engine for cleaning tables (NullPool avoids connection contention)
_clean_engine = create_async_engine(
    "postgresql+asyncpg://aos_user:aos_password@localhost:5432/aos_db",
    echo=False,
    poolclass=NullPool,
)

TestSessionFactory = async_sessionmaker(
    bind=app_engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    """Clean all tables before each test using TRUNCATE."""
    async with _clean_engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(
            text("TRUNCATE TABLE events, runs, tasks, approvals, workers, idempotency_keys RESTART IDENTITY CASCADE")
        )
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for the test."""
    async with TestSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP client for API tests."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
