"""Task application service — CRUD operations for Task entities."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aos.contracts.enums import TaskStatus
from aos.contracts.task import Task
from aos.contracts.transitions import (
    InvalidStateTransitionError,
    transition_task_abandon,
    transition_task_lock,
    transition_task_mark_ready,
    transition_task_release,
    transition_task_start,
    transition_task_unblock,
    transition_task_block,
)
from aos.db.models import TaskRow


class TaskNotFoundError(Exception):
    """Raised when a Task does not exist."""


class TaskService:
    """Manages Task lifecycle using Phase 0 transition functions.

    INVARIANT: Task status is only mutated via named Phase 0 transition
    functions. No direct ``UPDATE tasks SET status = …`` is issued.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(self, task_id: str) -> TaskRow:
        result = await self._session.execute(
            select(TaskRow).where(TaskRow.id == task_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise TaskNotFoundError(f"Task {task_id!r} not found.")
        return row

    async def list_all(self) -> list[TaskRow]:
        result = await self._session.execute(
            select(TaskRow).order_by(TaskRow.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        title: str,
        description: str = "",
        acceptance_criteria: list[str] | None = None,
        requirement_version: int = 0,
    ) -> TaskRow:
        row = TaskRow(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria or [],
            requirement_version=requirement_version,
            status=str(TaskStatus.DRAFT),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    # ------------------------------------------------------------------
    # Transitions (via Phase 0 functions)
    # ------------------------------------------------------------------

    async def lock(self, task_id: str) -> TaskRow:
        row = await self.get(task_id)
        task = _row_to_domain(row)
        result = transition_task_lock(task)
        return await _apply_task_result(row, result.entity, self._session)

    async def start(self, task_id: str) -> TaskRow:
        row = await self.get(task_id)
        task = _row_to_domain(row)
        result = transition_task_start(task)
        return await _apply_task_result(row, result.entity, self._session)

    async def block(self, task_id: str, reason: str) -> TaskRow:
        row = await self.get(task_id)
        task = _row_to_domain(row)
        result = transition_task_block(task, reason)
        return await _apply_task_result(row, result.entity, self._session)

    async def unblock(self, task_id: str) -> TaskRow:
        row = await self.get(task_id)
        task = _row_to_domain(row)
        result = transition_task_unblock(task)
        return await _apply_task_result(row, result.entity, self._session)

    async def mark_ready(self, task_id: str) -> TaskRow:
        row = await self.get(task_id)
        task = _row_to_domain(row)
        result = transition_task_mark_ready(task)
        return await _apply_task_result(row, result.entity, self._session)

    async def release(self, task_id: str, approval_id: str) -> TaskRow:
        row = await self.get(task_id)
        task = _row_to_domain(row)
        result = transition_task_release(task, approval_id)
        return await _apply_task_result(row, result.entity, self._session)

    async def abandon(self, task_id: str, reason: str) -> TaskRow:
        row = await self.get(task_id)
        task = _row_to_domain(row)
        result = transition_task_abandon(task, reason)
        return await _apply_task_result(row, result.entity, self._session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_domain(row: TaskRow) -> Task:
    """Reconstruct a Phase 0 Task domain object from a TaskRow."""
    return Task(
        id=row.id,
        title=row.title,
        description=row.description,
        acceptance_criteria=list(row.acceptance_criteria or []),
        requirement_version=row.requirement_version,
        status=TaskStatus(row.status),
        release_approval_id=row.release_approval_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _apply_task_result(
    row: TaskRow, updated: Task, session: AsyncSession
) -> TaskRow:
    """Write the updated Task domain fields back to the TaskRow."""
    row.status = str(updated.status)
    row.release_approval_id = updated.release_approval_id
    row.updated_at = updated.updated_at
    await session.flush()
    return row
