"""Async SQLAlchemy engine and session factory.

Configuration is loaded from the AOS_DATABASE_URL environment variable.
"""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_DATABASE_URL = os.environ.get(
    "AOS_DATABASE_URL",
    "postgresql+asyncpg://aos_user:aos_password@localhost:5432/aos_db",
)

# statement_timeout = 5000ms guards against long-running queries holding row locks.
engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    connect_args={"server_settings": {"statement_timeout": "5000"}},
)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)
