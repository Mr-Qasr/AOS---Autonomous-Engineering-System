"""Task domain contract."""

from datetime import datetime, timezone
from typing import List, Optional
import uuid

from pydantic import Field, field_validator

from aos.contracts.base import AOSBaseModel
from aos.contracts.enums import TaskStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Task(AOSBaseModel):
    """Represents an engineering objective, acceptance criteria, and policy assignment."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    objective: str
    requirement_version: int = Field(ge=1)
    acceptance_criteria: List[str]
    policy_id: str
    status: TaskStatus = Field(default=TaskStatus.DRAFT)
    allowed_scope: List[str] = Field(default_factory=list)
    release_approval_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("id", "objective", "policy_id")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v.strip()

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_acceptance_criteria(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("acceptance_criteria must contain at least one criterion.")
        for item in v:
            if not item or not item.strip():
                raise ValueError("Each acceptance criterion must be a non-empty string.")
        return [item.strip() for item in v]

