"""Tests for idempotency store including concurrent race conditions."""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from aos.tests.conftest import TestSessionFactory
from aos.workflow.idempotency import IdempotencyConflictError, IdempotencyStore


@pytest_asyncio.fixture
async def store(db_session: AsyncSession) -> IdempotencyStore:
    return IdempotencyStore(db_session)


@pytest.mark.asyncio
async def test_idempotency_lock_and_complete(store):
    """Test basic lock-complete flow."""
    await store.lock("run_start", "key-1", "hash-1")
    await store.complete("run_start", "key-1", 200, {"result": "ok"})
    await store._session.commit()

    # Should return cached result
    cached = await store.get_cached("run_start", "key-1", "hash-1")
    assert cached is not None
    assert cached["status"] == 200
    assert cached["body"] == {"result": "ok"}


@pytest.mark.asyncio
async def test_idempotency_same_key_different_hash_conflict(store):
    """Test that same key with different hash raises conflict."""
    await store.lock("run_start", "key-2", "hash-a")
    await store.complete("run_start", "key-2", 200, {"result": "a"})
    await store._session.commit()

    # Same key, different hash should raise conflict
    with pytest.raises(IdempotencyConflictError, match="different request payload"):
        await store.get_cached("run_start", "key-2", "hash-b")


@pytest.mark.asyncio
async def test_idempotency_in_flight_conflict(store):
    """Test that in-flight key raises conflict."""
    await store.lock("run_start", "key-3", "hash-3")
    await store._session.flush()

    # Key is locked (in-flight)
    with pytest.raises(IdempotencyConflictError, match="in-flight"):
        await store.get_cached("run_start", "key-3", "hash-3")


@pytest.mark.asyncio
async def test_idempotency_lock_conflict_on_concurrent_use(store):
    """Test that concurrent lock attempts result in one winner."""
    await store.lock("run_start", "key-4", "hash-4")
    await store._session.flush()

    # Second lock with same key should fail
    with pytest.raises(IdempotencyConflictError, match="already exists"):
        await store.lock("run_start", "key-4", "hash-4")


@pytest.mark.asyncio
async def test_idempotency_concurrent_race_db_safe():
    """Test that concurrent first-use race is DB-safe.

    Two concurrent tasks try to lock the same key. Exactly one should succeed.
    """
    async def try_lock(key: str, hash_val: str):
        async with TestSessionFactory() as session:
            store = IdempotencyStore(session)
            try:
                await store.lock("run_start", key, hash_val)
                await session.commit()
                return True
            except IdempotencyConflictError:
                await session.rollback()
                return False

    # Run 5 concurrent attempts for the same key
    results = await asyncio.gather(
        *[try_lock("race-key", "race-hash") for _ in range(5)]
    )

    # Exactly one should succeed
    assert sum(results) == 1, f"Expected exactly 1 success, got {sum(results)}"


@pytest.mark.asyncio
async def test_idempotency_different_keys_both_succeed(store):
    """Test that different keys can both be locked and completed."""
    await store.lock("run_start", "key-e", "hash-e")
    await store.lock("run_start", "key-f", "hash-f")
    await store._session.commit()

    # Complete both
    await store.complete("run_start", "key-e", 200, {"result": "e"})
    await store.complete("run_start", "key-f", 200, {"result": "f"})
    await store._session.commit()

    # Both should return cached results
    cached_e = await store.get_cached("run_start", "key-e", "hash-e")
    cached_f = await store.get_cached("run_start", "key-f", "hash-f")
    assert cached_e is not None
    assert cached_f is not None
    assert cached_e["status"] == 200
    assert cached_f["status"] == 200
