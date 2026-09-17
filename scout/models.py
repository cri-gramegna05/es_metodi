"""Normalized records exchanged between pipeline stages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Gender = Literal["men", "women", "unisex", "unknown"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Item(BaseModel):
    """A single product as seen on a source listing."""

    brand: str
    url: str
    title: str = ""
    price: float | None = None          # current (discounted) price
    full_price: float | None = None     # pre-discount price, when advertised
    currency: str = "EUR"
    category: str = "shoes"
    gender: Gender = "unknown"
    country: str | None = None          # brand country, when the source states it

    @field_validator("brand")
    @classmethod
    def _strip_brand(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty brand")
        return v

    @property
    def discount_pct(self) -> float | None:
        if self.price is None or not self.full_price or self.full_price <= 0:
            return None
        if self.price > self.full_price:
            return 0.0
        return round((1 - self.price / self.full_price) * 100, 1)


class Observation(BaseModel):
    """Per-brand aggregate of what one source shows about a brand."""

    brand: str
    source: str
    url: str
    price_min: float | None = None
    price_max: float | None = None
    currency: str = "EUR"
    discount_pct: float | None = None   # mean discount over discounted items
    discounted_share: float | None = None  # share of items on sale, 0-1
    sneaker_share: float | None = None     # share of items that look like sneakers, 0-1
    n_items: int = 0
    country: str | None = None
    category: str = "shoes"
    gender: Gender = "unknown"
    collected_at: datetime = Field(default_factory=utcnow)

    @property
    def price_range(self) -> tuple[float | None, float | None]:
        return (self.price_min, self.price_max)


class RuleResult(BaseModel):
    brand_slug: str
    passed: bool
    reasons: list[str] = Field(default_factory=list)   # why it was dropped
    signals: list[str] = Field(default_factory=list)   # positive signals hit
    prescore: int = 0                                  # 0-100, deterministic
