"""Initial schema — all Phase 1 tables + append-only event trigger.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-11 00:00:00.000000

"""

from typing import Sequence, Union

from sqlalchemy import DDL
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # tasks
    # -----------------------------------------------------------------------
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("acceptance_criteria", sa.dialects.postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("requirement_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("release_approval_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -----------------------------------------------------------------------
    # runs
    # -----------------------------------------------------------------------
    op.create_table(
        "runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), nullable=False, index=True),
        sa.Column("workflow_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("model_route", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("repair_attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_repair_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("checkpoint", sa.String(64), nullable=False, server_default="CP_INITIALIZED"),
        sa.Column("checkpoint_seq", sa.Integer, nullable=False, server_default="0"),
        sa.Column("checkpoint_metadata", sa.dialects.postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("current_event_sequence", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fencing_token", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -----------------------------------------------------------------------
    # events (append-only)
    # -----------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_events_run_sequence"),
    )

    # -----------------------------------------------------------------------
    # approvals
    # -----------------------------------------------------------------------
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("requester", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("justification", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -----------------------------------------------------------------------
    # workers
    # -----------------------------------------------------------------------
    op.create_table(
        "workers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("hostname", sa.String(256), nullable=False),
        sa.Column("capabilities", sa.dialects.postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("health", sa.String(32), nullable=False, server_default="healthy"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -----------------------------------------------------------------------
    # idempotency_keys
    # -----------------------------------------------------------------------
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", sa.dialects.postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resource_type", "idempotency_key", name="uq_idempotency_resource_key"),
    )

    # -----------------------------------------------------------------------
    # Append-only event trigger — prevents UPDATE/DELETE at DB layer
    # -----------------------------------------------------------------------
    op.execute(
        DDL(
            """
            CREATE OR REPLACE FUNCTION trg_events_no_update_delete_fn()
            RETURNS TRIGGER AS $$
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    RAISE EXCEPTION 'events table is append-only: UPDATE not allowed';
                ELSIF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'events table is append-only: DELETE not allowed';
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        DDL(
            """
            CREATE TRIGGER trg_events_no_update_delete
            BEFORE UPDATE OR DELETE ON events
            FOR EACH ROW
            EXECUTE FUNCTION trg_events_no_update_delete_fn();
            """
        )
    )


def downgrade() -> None:
    # Drop trigger and function
    op.execute(DDL("DROP TRIGGER IF EXISTS trg_events_no_update_delete ON events;"))
    op.execute(DDL("DROP FUNCTION IF EXISTS trg_events_no_update_delete_fn();"))

    # Drop tables in reverse order
    op.drop_table("idempotency_keys")
    op.drop_table("workers")
    op.drop_table("approvals")
    op.drop_table("events")
    op.drop_table("runs")
    op.drop_table("tasks")
