"""Approval CRUD endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aos.api.deps import get_db
from aos.db.models import ApprovalRow

router = APIRouter(prefix="/approvals", tags=["approvals"])

DB = Annotated[AsyncSession, Depends(get_db)]


class ApprovalCreateRequest(BaseModel):
    run_id: str
    action: str
    requester: str


class ApprovalDecideRequest(BaseModel):
    decision: str  # approved | rejected | expired
    decided_by: str
    justification: Optional[str] = None


class ApprovalResponse(BaseModel):
    id: str
    run_id: str
    action: str
    requester: str
    decision: str
    decided_by: Optional[str]
    justification: Optional[str]

    model_config = {"from_attributes": True}


def _to_response(row: ApprovalRow) -> ApprovalResponse:
    return ApprovalResponse(
        id=row.id,
        run_id=row.run_id,
        action=row.action,
        requester=row.requester,
        decision=row.decision,
        decided_by=row.decided_by,
        justification=row.justification,
    )


@router.post("", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
async def create_approval(body: ApprovalCreateRequest, db: DB) -> Any:
    row = ApprovalRow(
        id=str(uuid.uuid4()),
        run_id=body.run_id,
        action=body.action,
        requester=body.requester,
        decision="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(approval_id: str, db: DB) -> Any:
    result = await db.execute(
        select(ApprovalRow).where(ApprovalRow.id == approval_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id!r} not found.")
    return _to_response(row)


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str, body: ApprovalDecideRequest, db: DB
) -> Any:
    result = await db.execute(
        select(ApprovalRow).where(ApprovalRow.id == approval_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id!r} not found.")
    if body.decision not in {"approved", "rejected", "expired"}:
        raise HTTPException(status_code=422, detail="decision must be approved, rejected, or expired.")
    row.decision = body.decision
    row.decided_by = body.decided_by
    row.justification = body.justification
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)
