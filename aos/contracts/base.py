"""Base model for all AOS contracts enforcing immutability and strict schemas."""

from pydantic import BaseModel, ConfigDict


class AOSBaseModel(BaseModel):
    """Immutable base model for all AOS contract objects."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        use_enum_values=True,
    )

