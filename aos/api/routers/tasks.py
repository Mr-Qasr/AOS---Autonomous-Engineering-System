"""Task CRUD endpoints.

All state mutations go through TaskService which uses Phase 0 transition
functions. No raw status writes are issued from here.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aos.api.deps import get_db
from aos.contracts.transitions import InvalidStateTransitionError
from aos.db.models import TaskRow
from aos.services.task_service import TaskNotFoundError, TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    requirement_version: int = Field(default=0, ge=0)


class TaskTransitionRequest(BaseModel):
    reason: str = ""
    approval_id: str = ""


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    requirement_version: int
    status: str
    release_approval_id: str | None

    model_config = {"from_attributes": True}


def _to_response(row: TaskRow) -> TaskResponse:
    return TaskResponse(
        id=row.id,
        title=row.title,
        description=row.description,
        acceptance_criteria=list(row.acceptance_criteria or []),
        requirement_version=row.requirement_version,
        status=row.status,
        release_approval_id=row.release_approval_id,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[TaskResponse])
async def list_tasks(db: DB) -> Any:
    svc = TaskService(db)
    rows = await svc.list_all()
    return [_to_response(r) for r in rows]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreateRequest, db: DB) -> Any:
    svc = TaskService(db)
    row = await svc.create(
        title=body.title,
        description=body.description,
        acceptance_criteria=body.acceptance_criteria,
        requirement_version=body.requirement_version,
    )
    await db.commit()
    return _to_response(row)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: DB) -> Any:
    svc = TaskService(db)
    try:
        row = await svc.get(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/lock", response_model=TaskResponse)
async def lock_task(task_id: str, db: DB) -> Any:
    svc = TaskService(db)
    try:
        row = await svc.lock(task_id)
        await db.commit()
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/start", response_model=TaskResponse)
async def start_task(task_id: str, db: DB) -> Any:
    svc = TaskService(db)
    try:
        row = await svc.start(task_id)
        await db.commit()
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/block", response_model=TaskResponse)
async def block_task(task_id: str, body: TaskTransitionRequest, db: DB) -> Any:
    svc = TaskService(db)
    try:
        row = await svc.block(task_id, body.reason)
        await db.commit()
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/unblock", response_model=TaskResponse)
async def unblock_task(task_id: str, db: DB) -> Any:
    svc = TaskService(db)
    try:
        row = await svc.unblock(task_id)
        await db.commit()
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/ready", response_model=TaskResponse)
async def mark_task_ready(task_id: str, db: DB) -> Any:
    svc = TaskService(db)
    try:
        row = await svc.mark_ready(task_id)
        await db.commit()
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/release", response_model=TaskResponse)
async def release_task(task_id: str, body: TaskTransitionRequest, db: DB) -> Any:
    svc = TaskService(db)
    try:
        row = await svc.release(task_id, body.approval_id)
        await db.commit()
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/abandon", response_model=TaskResponse)
async def abandon_task(task_id: str, body: TaskTransitionRequest, db: DB) -> Any:
    svc = TaskService(db)
    try:
        row = await svc.abandon(task_id, body.reason)
        await db.commit()
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(row)
