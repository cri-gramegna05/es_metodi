"""Structured output contract for the classification step."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Positioning = Literal["luxury", "premium", "contemporary", "mass", "unknown"]
FounderType = Literal[
    "single_founder", "influencer", "family", "designer", "group", "institutional", "unknown"
]


class Classification(BaseModel):
    """What the local LLM must return, verbatim, as JSON."""

    is_italian: bool
    is_mens: bool
    positioning: Positioning
    founder_type: FounderType
    red_flags: list[str] = Field(default_factory=list, max_length=10)
    score: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=800)

    @field_validator("red_flags", mode="before")
    @classmethod
    def _coerce_flags(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return [str(x) for x in v] if isinstance(v, list) else []

    @field_validator("positioning", "founder_type", mode="before")
    @classmethod
    def _unknown_on_junk(cls, v: object) -> object:
        return v if isinstance(v, str) and v.strip() else "unknown"


def json_schema() -> dict:
    """Schema handed to Ollama's structured-output `format` field."""
    return Classification.model_json_schema()
