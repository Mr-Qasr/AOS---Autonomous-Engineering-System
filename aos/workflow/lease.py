"""Lease manager for workflow controller fencing.

A lease is an exclusive, time-bounded claim that a specific controller process
holds authority over a Run. The ``fencing_token`` is a monotonically-increasing
integer that prevents a stale controller (whose lease expired) from mutating
Run state even if it issues a late SQL UPDATE.

Lease semantics:
- Acquire:  Succeeds only if the lease slot is vacant (NULL) or has expired.
            Atomically increments ``fencing_token`` to invalidate any previous
            holder's token. Returns the new fencing token.
- Renew:    Succeeds only when ``lease_owner`` matches and fencing_token matches
            and lease has not yet expired. Does NOT change fencing_token.
- Release:  Clears lease_owner and lease_expiry. Only the current holder
            (identified by fencing_token) may release.

All three operations are single-statement ACID UPDATE…RETURNING queries so
they compose safely without additional application-level locking.

The mandatory repository transaction boundary also re-verifies the fencing
token via the WHERE clause of its UPDATE (step 8 in the spec), providing a
second, independent guard against stale writes.
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class StaleControllerFencingError(Exception):
    """Raised when a controller's fencing token is no longer valid."""


_CONTROLLER_ID: str = os.environ.get("AOS_CONTROLLER_ID", "default-controller")
_LEASE_TTL: int = int(os.environ.get("AOS_LEASE_TTL_SECONDS", "30"))


class LeaseManager:
    """Manages lease acquisition, renewal, and release for a single controller."""

    def __init__(
        self,
        session: AsyncSession,
        controller_id: str = _CONTROLLER_ID,
        lease_ttl_seconds: int = _LEASE_TTL,
    ) -> None:
        self._session = session
        self._controller_id = controller_id
        self._lease_ttl = lease_ttl_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self, run_id: str) -> int:
        """Attempt to acquire the lease for ``run_id``.

        Succeeds only if the lease slot is vacant or has expired.
        Increments ``fencing_token`` atomically.

        Returns:
            The new fencing token held by this controller.

        Raises:
            StaleControllerFencingError: if the lease is currently held by
                another (non-expired) controller.
        """
        expiry = _future(self._lease_ttl)
        result = await self._session.execute(
            text(
                """
                UPDATE runs
                SET
                    lease_owner    = :owner,
                    lease_expiry   = :expiry,
                    fencing_token  = fencing_token + 1,
                    updated_at     = NOW()
                WHERE
                    id = :run_id
                    AND (lease_expiry IS NULL OR lease_expiry < NOW())
                RETURNING fencing_token
                """
            ),
            {"owner": self._controller_id, "expiry": expiry, "run_id": run_id},
        )
        row = result.fetchone()
        if row is None:
            raise StaleControllerFencingError(
                f"Cannot acquire lease on run {run_id!r}: held by another active controller."
            )
        return int(row[0])

    async def renew(self, run_id: str, held_token: int) -> None:
        """Extend the lease expiry without changing the fencing token.

        Raises:
            StaleControllerFencingError: if the token no longer matches or the
                lease has already expired.
        """
        expiry = _future(self._lease_ttl)
        result = await self._session.execute(
            text(
                """
                UPDATE runs
                SET
                    lease_expiry = :expiry,
                    updated_at   = NOW()
                WHERE
                    id           = :run_id
                    AND lease_owner   = :owner
                    AND fencing_token = :token
                    AND lease_expiry  >= NOW()
                RETURNING id
                """
            ),
            {
                "expiry": expiry,
                "run_id": run_id,
                "owner": self._controller_id,
                "token": held_token,
            },
        )
        if result.fetchone() is None:
            raise StaleControllerFencingError(
                f"Lease renewal failed for run {run_id!r}: token {held_token} is stale or expired."
            )

    async def release(self, run_id: str, held_token: int) -> None:
        """Release the lease.  Only the current token holder may release.

        Raises:
            StaleControllerFencingError: if the token no longer matches.
        """
        result = await self._session.execute(
            text(
                """
                UPDATE runs
                SET
                    lease_owner  = NULL,
                    lease_expiry = NULL,
                    updated_at   = NOW()
                WHERE
                    id           = :run_id
                    AND fencing_token = :token
                RETURNING id
                """
            ),
            {"run_id": run_id, "token": held_token},
        )
        if result.fetchone() is None:
            raise StaleControllerFencingError(
                f"Lease release failed for run {run_id!r}: token {held_token} no longer matches."
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future(seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
