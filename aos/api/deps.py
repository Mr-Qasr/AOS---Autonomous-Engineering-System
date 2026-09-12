"""FastAPI dependency injection helpers."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from aos.db.engine import AsyncSessionFactory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session and close it after the request."""
    async with AsyncSessionFactory() as session:
        yield session
