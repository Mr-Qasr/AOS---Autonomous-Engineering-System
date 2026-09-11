"""Policy domain contracts (schemas only; no runtime execution engine in Phase 0)."""

from typing import Any, Dict, List, Optional
import uuid

from pydantic import Field, field_validator

from aos.contracts.base import AOSBaseModel
from aos.contracts.enums import PolicyEffect


class PolicyRule(AOSBaseModel):
    """Declarative statement permitting or denying a specific principal action on a resource."""

    principal: str
    action: str
    resource: str
    effect: PolicyEffect
    conditions: Optional[Dict[str, Any]] = None
    description: Optional[str] = None

    @field_validator("principal", "action", "resource")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v.strip()


class Policy(AOSBaseModel):
    """Collection of rules defining the security boundaries for a Task or system execution."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = Field(default=1, ge=1)
    description: str
    rules: List[PolicyRule] = Field(default_factory=list)

    @field_validator("id", "description")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v.strip()

