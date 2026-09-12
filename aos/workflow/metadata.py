"""Checkpoint metadata — strictly-typed Pydantic model.

``CheckpointMetadata`` is serialised into ``runs.checkpoint_metadata`` (JSONB).
It is an ``AOSBaseModel`` (frozen, extra=forbid) so deserialisation of corrupt
or unexpected data fails loudly rather than silently.
"""

from typing import Optional

from pydantic import Field

from aos.contracts.base import AOSBaseModel


class CheckpointMetadata(AOSBaseModel):
    """Typed metadata stored alongside the checkpoint cursor.

    Fields:
        step_name:         Human-readable name of the current workflow step.
        action_token:      Opaque idempotency token for the external action
                           dispatched in this step.  Format: "{run_id}:{step}:{cp_seq}".
                           None when no external action has been dispatched yet.
        attempt_number:    Repair attempt ordinal within this step (0 = initial attempt).
        step_input_digest: SHA-256 hex digest of the step's normalised input payload.
                           None when the step has no persisted input digest.
    """

    step_name: str
    action_token: Optional[str] = None
    attempt_number: int = Field(default=0, ge=0)
    step_input_digest: Optional[str] = None
