"""LLM backends. `ollama` is the real one; `stub` keeps the pipeline runnable offline."""

from __future__ import annotations

import json
import re
from typing import Protocol

import httpx

from ..config import ClassifyConfig
from ..log import get_logger

log = get_logger(__name__)


class Backend(Protocol):
    name: str

    def generate(self, system: str, messages: list[dict[str, str]], schema: dict) -> str:
        """Return the raw assistant text (expected to be a JSON object)."""


class OllamaBackend:
    """Local Ollama via /api/chat with structured output."""

    name = "ollama"

    def __init__(self, cfg: ClassifyConfig, client: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self.client = client or httpx.Client(timeout=cfg.timeout_seconds)

    def generate(self, system: str, messages: list[dict[str, str]], schema: dict) -> str:
        payload = {
            "model": self.cfg.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "format": schema,                      # Ollama structured outputs
            "options": {"temperature": self.cfg.temperature},
        }
        resp = self.client.post(f"{self.cfg.host.rstrip('/')}/api/chat", json=payload)
        if resp.status_code == 400:
            # Older servers reject a JSON-schema `format`; fall back to plain JSON mode.
            payload["format"] = "json"
            resp = self.client.post(f"{self.cfg.host.rstrip('/')}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message") or {}).get("content", "")

    def close(self) -> None:
        self.client.close()


class StubBackend:
    """Deterministic stand-in: reads the facts back out of the prompt.

    Not a model — it exists so the pipeline (and CI) can run with no Ollama around.
    """

    name = "stub"

    ITALIAN_HINTS = ("milano", "roma", "napoli", "firenze", "italia", "italy", "veneto")

    def generate(self, system: str, messages: list[dict[str, str]], schema: dict) -> str:
        text = "\n".join(m["content"] for m in messages)
        brand = self._field(text, "Brand") or "unknown"
        discount = self._number(text, "Mean discount on marketplaces")
        items = self._number(text, "Items seen")
        sneaker = self._number(text, "Share of sneakers in assortment")
        price_low, price_high = self._price_range(text)

        red_flags: list[str] = []
        score = 40
        if price_low and 250 <= price_low and price_high and price_high <= 700:
            score += 20
        if discount and discount >= 40:
            score += 20
        elif discount is not None and discount < 15:
            red_flags.append("little marketplace discounting")
        if items and items <= 30:
            score += 15
        elif items:
            red_flags.append("large assortment")
        if sneaker and sneaker > 50:
            red_flags.append("sneaker-first")
            score -= 25
        is_italian = any(h in brand.lower() for h in self.ITALIAN_HINTS) or "IT" in text

        return json.dumps({
            "is_italian": is_italian,
            "is_mens": "men" in text.lower(),
            "positioning": "premium" if price_high and price_high <= 700 else "luxury",
            "founder_type": "unknown",
            "red_flags": red_flags,
            "score": max(0, min(100, score)),
            "rationale": (
                f"Stub backend: price {price_low}-{price_high} EUR, "
                f"{discount if discount is not None else '?'}% mean discount, {items} items."
            ),
        })

    @staticmethod
    def _field(text: str, label: str) -> str | None:
        match = re.search(rf"^{label}: (.+)$", text, re.M)
        return match.group(1).strip() if match else None

    @classmethod
    def _number(cls, text: str, label: str) -> float | None:
        value = cls._field(text, label)
        if not value:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", value)
        return float(match.group(1)) if match else None

    @classmethod
    def _price_range(cls, text: str) -> tuple[float | None, float | None]:
        value = cls._field(text, "Retail price range") or ""
        match = re.search(r"(\d+)-(\d+)", value)
        return (float(match.group(1)), float(match.group(2))) if match else (None, None)


def build_backend(cfg: ClassifyConfig, client: httpx.Client | None = None) -> Backend:
    if cfg.backend == "stub":
        return StubBackend()
    if cfg.backend == "ollama":
        return OllamaBackend(cfg, client)
    raise KeyError(f"unknown classify backend: {cfg.backend!r} (known: ollama, stub)")
