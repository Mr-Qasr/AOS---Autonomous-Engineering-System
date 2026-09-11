"""Event domain contract and typed event payload definitions."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from pydantic import Field, field_validator, model_validator

from aos.contracts.base import AOSBaseModel
from aos.contracts.enums import EventType, FailureClass, RunStatus, TaskStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RepairAttemptPayload(AOSBaseModel):
    """Strict schema for repair.attempt event payload per Master Specification §6."""

    failure_class: FailureClass
    hypothesis: str
    patch_sha: str
    result: str

    @field_validator("hypothesis", "patch_sha", "result")
    @classmethod
    def validate_non_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v.strip()


class RunStateChangedPayload(AOSBaseModel):
    """Payload for run.state.changed event."""

    previous_status: RunStatus
    new_status: RunStatus
    repair_attempt_count: int = Field(ge=0)
    details: Optional[Dict[str, Any]] = None


class TaskStateChangedPayload(AOSBaseModel):
    """Payload for task.state.changed event."""

    previous_status: TaskStatus
    new_status: TaskStatus
    details: Optional[Dict[str, Any]] = None


class Event(AOSBaseModel):
    """Immutable record in the append-only event stream."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    sequence: int = Field(ge=1)
    type: EventType
    timestamp: datetime = Field(default_factory=_utc_now)
    actor: str
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "run_id", "actor")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v.strip()

    @model_validator(mode="after")
    def validate_event_payload(self) -> "Event":
        if self.type == EventType.REPAIR_ATTEMPT:
            # Validate that payload strictly satisfies RepairAttemptPayload
            RepairAttemptPayload.model_validate(self.payload)
        return self

