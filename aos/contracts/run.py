"""Run domain contract."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from pydantic import Field, field_validator

from aos.contracts.base import AOSBaseModel
from aos.contracts.enums import RunStatus

DEFAULT_MAX_REPAIR_ATTEMPTS: int = 3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Run(AOSBaseModel):
    """Represents an execution attempt of an engineering Task workflow."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    workflow_version: str = Field(default="1.0.0")
    worker_id: Optional[str] = Field(default=None)
    model_route: Optional[str] = Field(default=None)
    status: RunStatus = Field(default=RunStatus.QUEUED)
    repair_attempt_count: int = Field(default=0, ge=0)
    max_repair_attempts: int = Field(default=DEFAULT_MAX_REPAIR_ATTEMPTS, ge=1)
    started_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("id", "task_id", "workflow_version")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v.strip()

    @field_validator("worker_id", "model_route")
    @classmethod
    def validate_optional_strings(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError(f"{info.field_name} cannot be an empty or whitespace string.")
        return v.strip() if v is not None else None

