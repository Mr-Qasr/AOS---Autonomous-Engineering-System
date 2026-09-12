"""Run lifecycle endpoints.

All state mutations go through RunService which uses the RunRepository
transaction boundary (fencing + Phase 0 transition + checkpoint DAG + event).
"""

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aos.api.deps import get_db
from aos.contracts.transitions import InvalidStateTransitionError
from aos.db.models import RunRow
from aos.services.run_service import RunService
from aos.workflow.checkpoints import InvalidCheckpointTransitionError
from aos.workflow.idempotency import IdempotencyConflictError
from aos.workflow.lease import StaleControllerFencingError
from aos.workflow.repository import RunNotFoundError

router = APIRouter(prefix="/runs", tags=["runs"])

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RunCreateRequest(BaseModel):
    task_id: str
    workflow_version: str = "1.0.0"
    worker_id: Optional[str] = None
    model_route: Optional[str] = None


class RunTransitionRequest(BaseModel):
    worker_id: Optional[str] = None
    reason: str = ""
    held_token: Optional[int] = None
    idempotency_key: Optional[str] = None


class RunRepairDispatchRequest(BaseModel):
    held_token: int
    failure_class: str
    hypothesis: str
    patch_sha: str
    result: str


class RunResponse(BaseModel):
    id: str
    task_id: str
    workflow_version: str
    worker_id: Optional[str]
    model_route: Optional[str]
    status: str
    repair_attempt_count: int
    max_repair_attempts: int
    checkpoint: str
    checkpoint_seq: int
    fencing_token: int
    started_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}


def _to_response(row: RunRow) -> RunResponse:
    return RunResponse(
        id=row.id,
        task_id=row.task_id,
        workflow_version=row.workflow_version,
        worker_id=row.worker_id,
        model_route=row.model_route,
        status=row.status,
        repair_attempt_count=row.repair_attempt_count,
        max_repair_attempts=row.max_repair_attempts,
        checkpoint=row.checkpoint,
        checkpoint_seq=row.checkpoint_seq,
        fencing_token=row.fencing_token,
        started_at=row.started_at,
        updated_at=row.updated_at,
    )


def _handle_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, RunNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (InvalidStateTransitionError, InvalidCheckpointTransitionError)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (StaleControllerFencingError, IdempotencyConflictError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(body: RunCreateRequest, db: DB) -> Any:
    svc = RunService(db)
    row = await svc.create(
        task_id=body.task_id,
        workflow_version=body.workflow_version,
        worker_id=body.worker_id,
        model_route=body.model_route,
    )
    return _to_response(row)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, db: DB) -> Any:
    svc = RunService(db)
    try:
        row = await svc.get(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(row)


@router.get("/task/{task_id}", response_model=list[RunResponse])
async def list_runs_for_task(task_id: str, db: DB) -> Any:
    svc = RunService(db)
    rows = await svc.list_by_task(task_id)
    return [_to_response(r) for r in rows]


@router.post("/{run_id}/start", response_model=RunResponse)
async def start_run(run_id: str, body: RunTransitionRequest, db: DB) -> Any:
    svc = RunService(db)
    try:
        row = await svc.start(
            run_id,
            worker_id=body.worker_id,
            idempotency_key=body.idempotency_key,
        )
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)


@router.post("/{run_id}/pass", response_model=RunResponse)
async def pass_run(run_id: str, body: RunTransitionRequest, db: DB) -> Any:
    if body.held_token is None:
        raise HTTPException(status_code=400, detail="held_token is required.")
    svc = RunService(db)
    try:
        row = await svc.mark_passed(run_id, body.held_token)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)


@router.post("/{run_id}/fail", response_model=RunResponse)
async def fail_run(run_id: str, body: RunTransitionRequest, db: DB) -> Any:
    if body.held_token is None:
        raise HTTPException(status_code=400, detail="held_token is required.")
    svc = RunService(db)
    try:
        row = await svc.mark_failed(run_id, body.held_token, reason=body.reason or None)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)


@router.post("/{run_id}/enter-repair", response_model=RunResponse)
async def enter_repair(run_id: str, body: RunTransitionRequest, db: DB) -> Any:
    if body.held_token is None:
        raise HTTPException(status_code=400, detail="held_token is required.")
    svc = RunService(db)
    try:
        row = await svc.enter_repair(run_id, body.held_token)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)


@router.post("/{run_id}/escalate", response_model=RunResponse)
async def escalate_run(run_id: str, body: RunTransitionRequest, db: DB) -> Any:
    if body.held_token is None:
        raise HTTPException(status_code=400, detail="held_token is required.")
    svc = RunService(db)
    try:
        row = await svc.escalate(run_id, body.held_token, reason=body.reason)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: str, body: RunTransitionRequest, db: DB) -> Any:
    svc = RunService(db)
    try:
        row = await svc.cancel(run_id, reason=body.reason, held_token=body.held_token)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)


@router.post("/{run_id}/lease/acquire")
async def acquire_run_lease(run_id: str, db: DB) -> Any:
    """Acquire (or take over) the Run lease — explicit recovery path.

    After a controller crash/restart, the replacement controller calls this to
    obtain a fresh fencing token (the old token is invalidated) and then resumes
    the Run through the transition endpoints. Succeeds only when the lease slot
    is vacant or expired; otherwise 409.
    """
    svc = RunService(db)
    try:
        token = await svc.acquire_lease(run_id)
        row = await svc.get(run_id)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return {
        "run_id": run_id,
        "held_token": token,
        "lease_owner": row.lease_owner,
        "lease_expiry": row.lease_expiry,
    }


@router.post("/{run_id}/prepare-step", response_model=RunResponse)
async def prepare_step(run_id: str, body: RunTransitionRequest, db: DB) -> Any:
    if body.held_token is None:
        raise HTTPException(status_code=400, detail="held_token is required.")
    svc = RunService(db)
    try:
        row = await svc.prepare_step(run_id, body.held_token)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)


@router.post("/{run_id}/commit-step", response_model=RunResponse)
async def commit_step(run_id: str, body: RunTransitionRequest, db: DB) -> Any:
    if body.held_token is None:
        raise HTTPException(status_code=400, detail="held_token is required.")
    svc = RunService(db)
    try:
        row = await svc.commit_step(run_id, body.held_token)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)


@router.post("/{run_id}/dispatch-repair", response_model=RunResponse)
async def dispatch_repair(
    run_id: str, body: RunRepairDispatchRequest, db: DB
) -> Any:
    from aos.contracts.event import RepairAttemptPayload

    svc = RunService(db)
    try:
        payload = RepairAttemptPayload(
            failure_class=body.failure_class,
            hypothesis=body.hypothesis,
            patch_sha=body.patch_sha,
            result=body.result,
        )
        row = await svc.dispatch_repair(run_id, body.held_token, payload)
    except Exception as exc:
        raise _handle_errors(exc) from exc
    return _to_response(row)
