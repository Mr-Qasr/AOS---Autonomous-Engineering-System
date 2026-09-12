"""Alembic environment configuration.

Supports both offline and online migration modes.
Uses async engine for online migrations (asyncpg) and the sync URL
(from AOS_SYNC_DATABASE_URL) is not needed here because we use
asyncpg directly via asyncio.run().
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Alembic Config object
config = context.config

# Configure logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import ALL model classes so that Base.metadata is fully populated.
from aos.db.models import Base  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_database_url() -> str:
    """Read the async database URL from environment."""
    url = os.environ.get(
        "AOS_DATABASE_URL",
        "postgresql+asyncpg://aos_user:aos_password@localhost:5432/aos_db",
    )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This calls context.configure() with just a URL and not an Engine.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Execute migrations against a given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
