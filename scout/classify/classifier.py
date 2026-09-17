"""Calls the backend, validates the JSON, retries with the error in hand."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ..config import ClassifyConfig
from ..log import get_logger
from ..rules import BrandView
from .backends import Backend, build_backend
from .prompts import SYSTEM, retry_prompt, user_prompt
from .schema import Classification, json_schema

log = get_logger(__name__)
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


class ClassificationFailed(RuntimeError):
    """The model never produced JSON matching the schema."""


def extract_json(raw: str) -> dict:
    """Tolerate code fences and leading prose around the object."""
    text = _FENCE_RE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


class Classifier:
    def __init__(self, cfg: ClassifyConfig, backend: Backend | None = None) -> None:
        self.cfg = cfg
        self.backend = backend or build_backend(cfg)
        self.schema = json_schema()

    def classify(self, view: BrandView) -> Classification:
        messages = [{"role": "user", "content": user_prompt(view)}]
        last_error = "no attempt made"
        for attempt in range(1, self.cfg.max_retries + 1):
            raw = self.backend.generate(SYSTEM, messages, self.schema)
            try:
                return Classification.model_validate(extract_json(raw))
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                last_error = str(exc)
                log.warning("classification_invalid", brand=view.slug,
                            attempt=attempt, error=last_error[:200])
                messages += [
                    {"role": "assistant", "content": raw[:2000]},
                    {"role": "user", "content": retry_prompt(raw, last_error)},
                ]
        raise ClassificationFailed(f"{view.slug}: {last_error[:300]}")
