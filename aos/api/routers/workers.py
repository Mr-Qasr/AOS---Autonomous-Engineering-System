"""Worker registration endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aos.api.deps import get_db
from aos.db.models import WorkerRow

router = APIRouter(prefix="/workers", tags=["workers"])

DB = Annotated[AsyncSession, Depends(get_db)]


class WorkerRegisterRequest(BaseModel):
    id: Optional[str] = None
    hostname: str
    capabilities: list[str] = []


class WorkerHeartbeatRequest(BaseModel):
    health: str = "healthy"


class WorkerResponse(BaseModel):
    id: str
    hostname: str
    capabilities: list[str]
    health: str
    last_heartbeat: Optional[Any]

    model_config = {"from_attributes": True}


def _to_response(row: WorkerRow) -> WorkerResponse:
    return WorkerResponse(
        id=row.id,
        hostname=row.hostname,
        capabilities=list(row.capabilities or []),
        health=row.health,
        last_heartbeat=row.last_heartbeat,
    )


@router.post("", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
async def register_worker(body: WorkerRegisterRequest, db: DB) -> Any:
    row = WorkerRow(
        id=body.id or str(uuid.uuid4()),
        hostname=body.hostname,
        capabilities=body.capabilities,
        health="healthy",
        registered_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.get("", response_model=list[WorkerResponse])
async def list_workers(db: DB) -> Any:
    result = await db.execute(select(WorkerRow).order_by(WorkerRow.registered_at.desc()))
    return [_to_response(r) for r in result.scalars().all()]


@router.get("/{worker_id}", response_model=WorkerResponse)
async def get_worker(worker_id: str, db: DB) -> Any:
    result = await db.execute(select(WorkerRow).where(WorkerRow.id == worker_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id!r} not found.")
    return _to_response(row)


@router.post("/{worker_id}/heartbeat", response_model=WorkerResponse)
async def heartbeat(worker_id: str, body: WorkerHeartbeatRequest, db: DB) -> Any:
    result = await db.execute(select(WorkerRow).where(WorkerRow.id == worker_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id!r} not found.")
    if body.health not in {"healthy", "degraded", "unhealthy", "draining"}:
        raise HTTPException(status_code=422, detail=f"Invalid health value: {body.health!r}.")
    row.health = body.health
    row.last_heartbeat = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)
