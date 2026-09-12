"""SQLAlchemy ORM models for the AOS persistence layer.

Design invariants:
- Every table uses UUID string PKs matching Phase 0 Pydantic contracts.
- RunRow carries the full checkpoint cursor and fencing/lease fields needed
  by the workflow controller — these are persistence metadata, NOT domain
  status. Domain status is only changed via Phase 0 transition functions.
- EventRow is append-only; the DB trigger ``trg_events_no_update_delete``
  enforces this at the PostgreSQL layer (defined in the Alembic migration).
- No raw ``UPDATE runs SET status = ...`` is ever issued from application code.
  All status mutations go through the RunRepository transaction boundary.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class TaskRow(Base):
    """Persistent representation of a Task domain object."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    acceptance_criteria: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    requirement_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    release_approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

class RunRow(Base):
    """Persistent representation of a Run domain object + workflow metadata.

    Workflow metadata fields (checkpoint, checkpoint_seq, checkpoint_metadata,
    current_event_sequence, lease_owner, lease_expiry, fencing_token) are
    controller infrastructure — not domain state. They are never surfaced
    directly in API responses; they are read/written only by RunRepository.
    """

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workflow_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_route: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Domain state — only mutated via Phase 0 transition functions.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    repair_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_repair_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Workflow checkpoint cursor — infrastructure metadata.
    checkpoint: Mapped[str] = mapped_column(String(64), nullable=False, default="CP_INITIALIZED")
    checkpoint_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Monotonic event sequence counter — allocated under row lock.
    current_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Lease / fencing fields.
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


# ---------------------------------------------------------------------------
# Events (append-only)
# ---------------------------------------------------------------------------

class EventRow(Base):
    """Append-only event log entry.

    The ``trg_events_no_update_delete`` trigger prevents any UPDATE or DELETE
    on this table at the PostgreSQL layer, making the append-only guarantee
    independent of application-layer enforcement.

    ``sequence`` is allocated under the parent RunRow's exclusive lock so
    it is gapless and contiguous per run.
    """

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_events_run_sequence"),
    )


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

class ApprovalRow(Base):
    """Persistent record of an operator approval decision."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    requester: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class WorkerRow(Base):
    """Registration record for an execution worker."""

    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(256), nullable=False)
    capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    health: Mapped[str] = mapped_column(String(32), nullable=False, default="healthy")
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


# ---------------------------------------------------------------------------
# Idempotency Keys
# ---------------------------------------------------------------------------

class IdempotencyKeyRow(Base):
    """Idempotency store for client-supplied idempotency keys.

    Scope: (resource_type, idempotency_key).
    A completed response is cached so that duplicate requests return the
    same response body without re-executing the operation.
    """

    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "resource_type", "idempotency_key", name="uq_idempotency_resource_key"
        ),
    )
