"""Tests for database schema, migrations, and append-only event trigger."""

import pathlib
import subprocess
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aos.db.engine import engine

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture
async def db_conn():
    """Provide a raw database connection."""
    async with engine.connect() as conn:
        yield conn


@pytest.mark.asyncio
async def test_all_tables_exist(db_conn):
    """Verify all required Phase 1 tables exist."""
    result = await db_conn.execute(
        text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename NOT LIKE 'alembic%'
        """)
    )
    tables = {row[0] for row in result.fetchall()}
    expected = {"tasks", "runs", "events", "approvals", "workers", "idempotency_keys"}
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


@pytest.mark.asyncio
async def test_runs_table_has_checkpoint_fields(db_conn):
    """Verify runs table has all checkpoint/fencing fields."""
    result = await db_conn.execute(
        text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'runs' AND table_schema = 'public'
        """)
    )
    columns = {row[0] for row in result.fetchall()}
    expected = {
        "id", "task_id", "workflow_version", "worker_id", "model_route",
        "status", "repair_attempt_count", "max_repair_attempts",
        "checkpoint", "checkpoint_seq", "checkpoint_metadata",
        "current_event_sequence", "lease_owner", "lease_expiry",
        "fencing_token", "started_at", "updated_at",
    }
    assert expected.issubset(columns), f"Missing columns: {expected - columns}"


@pytest.mark.asyncio
async def test_events_table_unique_constraint(db_conn):
    """Verify unique constraint on (run_id, sequence)."""
    result = await db_conn.execute(
        text("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = 'events' AND constraint_type = 'UNIQUE'
        """)
    )
    constraints = {row[0] for row in result.fetchall()}
    assert "uq_events_run_sequence" in constraints


@pytest.mark.asyncio
async def test_idempotency_keys_unique_constraint(db_conn):
    """Verify unique constraint on (resource_type, idempotency_key)."""
    result = await db_conn.execute(
        text("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = 'idempotency_keys' AND constraint_type = 'UNIQUE'
        """)
    )
    constraints = {row[0] for row in result.fetchall()}
    assert "uq_idempotency_resource_key" in constraints


@pytest.mark.asyncio
async def test_idempotency_keys_has_request_hash(db_conn):
    """Verify idempotency_keys table has request_hash column."""
    result = await db_conn.execute(
        text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'idempotency_keys' AND table_schema = 'public'
        """)
    )
    columns = {row[0] for row in result.fetchall()}
    assert "request_hash" in columns


@pytest.mark.asyncio
async def test_events_append_only_trigger_blocks_update(db_conn):
    """Verify the append-only trigger prevents UPDATE on events."""
    now = datetime.now(timezone.utc)
    await db_conn.execute(text(
        "INSERT INTO tasks (id, title, acceptance_criteria, requirement_version, status, created_at, updated_at) VALUES ('t1', 'Test', '[]', 1, 'DRAFT', :now, :now)"
    ), {"now": now})
    await db_conn.execute(text(
        "INSERT INTO runs (id, task_id, started_at, updated_at) VALUES ('r1', 't1', :now, :now)"
    ), {"now": now})
    await db_conn.execute(text(
        "INSERT INTO events (id, run_id, sequence, type, actor, timestamp) VALUES ('e1', 'r1', 1, 'test', 'tester', :now)"
    ), {"now": now})
    await db_conn.commit()

    with pytest.raises(Exception, match="append-only"):
        await db_conn.execute(text("UPDATE events SET type = 'changed' WHERE id = 'e1'"))
        await db_conn.commit()
    await db_conn.rollback()


@pytest.mark.asyncio
async def test_events_append_only_trigger_blocks_delete(db_conn):
    """Verify the append-only trigger prevents DELETE on events."""
    now = datetime.now(timezone.utc)
    await db_conn.execute(text(
        "INSERT INTO tasks (id, title, acceptance_criteria, requirement_version, status, created_at, updated_at) VALUES ('t2', 'Test', '[]', 1, 'DRAFT', :now, :now)"
    ), {"now": now})
    await db_conn.execute(text(
        "INSERT INTO runs (id, task_id, started_at, updated_at) VALUES ('r2', 't2', :now, :now)"
    ), {"now": now})
    await db_conn.execute(text(
        "INSERT INTO events (id, run_id, sequence, type, actor, timestamp) VALUES ('e2', 'r2', 1, 'test', 'tester', :now)"
    ), {"now": now})
    await db_conn.commit()

    with pytest.raises(Exception, match="append-only"):
        await db_conn.execute(text("DELETE FROM events WHERE id = 'e2'"))
        await db_conn.commit()
    await db_conn.rollback()


@pytest.mark.asyncio
async def test_events_insert_allowed(db_conn):
    """Verify INSERT is still allowed on events."""
    now = datetime.now(timezone.utc)
    await db_conn.execute(text(
        "INSERT INTO tasks (id, title, acceptance_criteria, requirement_version, status, created_at, updated_at) VALUES ('t3', 'Test', '[]', 1, 'DRAFT', :now, :now)"
    ), {"now": now})
    await db_conn.execute(text(
        "INSERT INTO runs (id, task_id, started_at, updated_at) VALUES ('r3', 't3', :now, :now)"
    ), {"now": now})
    await db_conn.execute(text(
        "INSERT INTO events (id, run_id, sequence, type, actor, timestamp) VALUES ('e3', 'r3', 1, 'test', 'tester', :now)"
    ), {"now": now})
    await db_conn.commit()

    result = await db_conn.execute(text("SELECT count(*) FROM events WHERE id = 'e3'"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_no_schema_drift_between_orm_and_migrations(db_conn):
    """Verify the live database schema matches the ORM metadata (no drift).

    Runs ``alembic check`` against the configured database. Alembic compares
    the migration-managed schema with ``Base.metadata`` and reports any
    difference, catching ORM model changes that were never reflected in a
    migration. Like every other test in this module, it requires the database
    to be at ``alembic upgrade head``.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(_REPO_ROOT), timeout=120,
    )
    assert proc.returncode == 0, (
        "Schema drift detected (ORM metadata vs migration-managed schema):\n"
        + proc.stdout
        + "\n"
        + proc.stderr
    )
    assert "No new upgrade operations detected" in proc.stdout + proc.stderr
