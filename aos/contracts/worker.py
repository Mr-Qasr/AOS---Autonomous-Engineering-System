"""Worker domain contract."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import Field, field_validator

from aos.contracts.base import AOSBaseModel
from aos.contracts.enums import WorkerHealth


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Worker(AOSBaseModel):
    """Execution node registration, health status, and lease tracking."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    capabilities: List[str] = Field(default_factory=list)
    health: WorkerHealth = Field(default=WorkerHealth.HEALTHY)
    lease_expiry: Optional[datetime] = Field(default=None)
    cost_metadata: Dict[str, Any] = Field(default_factory=dict)
    registered_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Worker id must be a non-empty string.")
        return v.strip()

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: List[str]) -> List[str]:
        for cap in v:
            if not cap or not cap.strip():
                raise ValueError("Capability must be a non-empty string.")
        return [cap.strip() for cap in v]

