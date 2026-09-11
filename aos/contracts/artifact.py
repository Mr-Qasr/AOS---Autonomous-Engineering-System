"""Artifact domain contract."""

from datetime import datetime, timezone
import re
import uuid

from pydantic import Field, field_validator

from aos.contracts.base import AOSBaseModel

_SHA256_HEX_REGEX = re.compile(r"^[0-9a-fA-F]{64}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Artifact(AOSBaseModel):
    """Immutable evidence produced during a run (diffs, test logs, review reports)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    producer: str
    uri: str
    sha256: str
    run_id: str
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("id", "type", "producer", "uri", "run_id")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return v.strip()

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not _SHA256_HEX_REGEX.match(cleaned):
            raise ValueError("sha256 must be a 64-character hexadecimal string.")
        return cleaned

