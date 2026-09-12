"""Event read endpoints (append-only — no write endpoints exposed here)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aos.api.deps import get_db
from aos.db.models import EventRow
from aos.services.run_service import RunService
from aos.workflow.repository import RunNotFoundError

router = APIRouter(prefix="/runs/{run_id}/events", tags=["events"])

DB = Annotated[AsyncSession, Depends(get_db)]


class EventResponse(BaseModel):
    id: str
    run_id: str
    sequence: int
    type: str
    timestamp: Any
    actor: str
    payload: dict

    model_config = {"from_attributes": True}


def _to_response(row: EventRow) -> EventResponse:
    return EventResponse(
        id=row.id,
        run_id=row.run_id,
        sequence=row.sequence,
        type=row.type,
        timestamp=row.timestamp,
        actor=row.actor,
        payload=dict(row.payload or {}),
    )


@router.get("", response_model=list[EventResponse])
async def list_events(run_id: str, db: DB) -> Any:
    svc = RunService(db)
    try:
        rows = await svc.list_events(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_to_response(r) for r in rows]
