"""Idempotency store — prevents duplicate side effects from replayed requests.

Scope: (resource_type, idempotency_key).
A client supplies an ``Idempotency-Key`` header. On first request the operation
executes and the response is cached. On replay the cached response is returned
without re-executing the operation.

Phase 1 implements the core store. Principal/authentication scoping is deferred
to Phase 12 (Release Gates).
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aos.db.models import IdempotencyKeyRow


class IdempotencyConflictError(Exception):
    """Raised when a request with the same key is already in-flight."""


class IdempotencyStore:
    """Manages idempotency key locking and response caching."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_cached(
        self, resource_type: str, idempotency_key: str, request_hash: str
    ) -> dict[str, Any] | None:
        """Return cached response if this key was already completed with the same hash.

        Raises:
            IdempotencyConflictError: if the key exists but with a different hash
                (same key, different payload) or if the request is in-flight.
        """
        result = await self._session.execute(
            select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.resource_type == resource_type,
                IdempotencyKeyRow.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if row.locked:
            raise IdempotencyConflictError(
                f"Request with Idempotency-Key {idempotency_key!r} is already in-flight."
            )
        if row.request_hash != request_hash:
            raise IdempotencyConflictError(
                f"Idempotency-Key {idempotency_key!r} already exists for {resource_type!r} "
                f"with a different request payload."
            )
        return {"status": row.response_status, "body": row.response_body}

    async def lock(
        self, resource_type: str, idempotency_key: str, request_hash: str
    ) -> None:
        """Reserve this key as in-flight. Raises if a concurrent request beat us."""
        stmt = (
            pg_insert(IdempotencyKeyRow)
            .values(
                resource_type=resource_type,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_status=0,
                response_body={},
                locked=True,
            )
            .on_conflict_do_nothing(
                constraint="uq_idempotency_resource_key"
            )
            .returning(IdempotencyKeyRow.id)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        if result.fetchone() is None:
            raise IdempotencyConflictError(
                f"Idempotency-Key {idempotency_key!r} already exists for {resource_type!r}."
            )

    async def complete(
        self,
        resource_type: str,
        idempotency_key: str,
        status_code: int,
        body: dict[str, Any],
    ) -> None:
        """Record the completed response and unlock the key."""
        result = await self._session.execute(
            select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.resource_type == resource_type,
                IdempotencyKeyRow.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.response_status = status_code
        row.response_body = body
        row.locked = False
        await self._session.flush()
