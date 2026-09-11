"""Approval domain contract."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import Field, field_validator

from aos.contracts.base import AOSBaseModel
from aos.contracts.enums import ApprovalDecision


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Approval(AOSBaseModel):
    """Explicit authorization record granted for consequential actions."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: str
    evidence_refs: List[str] = Field(default_factory=list)
    actor: str
    scope: Dict[str, Any] = Field(default_factory=dict)
    expiry: datetime
    decision: ApprovalDecision = Field(default=ApprovalDecision.PENDING)
    decided_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("id", "action", "actor")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v.strip()

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, v: List[str]) -> List[str]:
        for ref in v:
            if not ref or not ref.strip():
                raise ValueError("Evidence reference must be a non-empty string.")
        return [ref.strip() for ref in v]

