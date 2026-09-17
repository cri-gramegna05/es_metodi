"""Collector contract: yield raw items, get normalized per-brand observations."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from statistics import mean
from typing import Iterator

from ..config import SourceConfig
from ..http import Fetcher
from ..log import get_logger
from ..models import Item, Observation

log = get_logger(__name__)

SNEAKER_RE = re.compile(
    r"\b(sneaker|sneakers|trainer|trainers|running|court|runner|skate)\b", re.I
)
PRICE_RE = re.compile(r"(\d[\d.,\s]*)")


def parse_price(text: str | None) -> float | None:
    """'€ 1.234,50' / '1,234.50 EUR' / '450' -> float."""
    if not text:
        return None
    match = PRICE_RE.search(text.replace("\xa0", " "))
    if not match:
        return None
    raw = match.group(1).strip().replace(" ", "")
    if "," in raw and "." in raw:
        # The rightmost separator is the decimal one.
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") \
            else raw.replace(",", "")
    elif "," in raw:
        # A 3-digit tail means thousands ("1.200"), anything else is decimals ("12,5").
        raw = raw.replace(",", "") if len(raw.split(",")[-1]) == 3 else raw.replace(",", ".")
    elif raw.count(".") == 1 and len(raw.split(".")[-1]) == 3:
        raw = raw.replace(".", "")  # thousands separator, not decimals
    try:
        return round(float(raw), 2)
    except ValueError:
        return None


class Collector(ABC):
    """One source. Subclasses only implement iter_items()."""

    type: str = "base"

    def __init__(self, name: str, cfg: SourceConfig, fetcher: Fetcher) -> None:
        self.name = name
        self.cfg = cfg
        self.fetcher = fetcher
        self.log = log.bind(source=name)

    @abstractmethod
    def iter_items(self) -> Iterator[Item]:
        """Yield one Item per product found on the source."""

    def collect(self) -> list[Observation]:
        items_by_brand: dict[str, list[Item]] = defaultdict(list)
        for item in self.iter_items():
            items_by_brand[item.brand].append(item)
        observations = [self.aggregate(brand, items) for brand, items in items_by_brand.items()]
        self.log.info("collected", brands=len(observations),
                      items=sum(o.n_items for o in observations))
        return observations

    def aggregate(self, brand: str, items: list[Item]) -> Observation:
        prices = [i.price for i in items if i.price is not None]
        discounts = [d for d in (i.discount_pct for i in items) if d is not None and d > 0]
        genders = {i.gender for i in items if i.gender != "unknown"}
        countries = {i.country for i in items if i.country}
        return Observation(
            brand=brand,
            source=self.name,
            url=self.brand_url(brand, items),
            price_min=min(prices) if prices else None,
            price_max=max(prices) if prices else None,
            currency=items[0].currency if items else "EUR",
            discount_pct=round(mean(discounts), 1) if discounts else 0.0,
            discounted_share=round(len(discounts) / len(items), 3) if items else None,
            sneaker_share=round(
                sum(1 for i in items if SNEAKER_RE.search(f"{i.title} {i.category}")) / len(items), 3
            ) if items else None,
            n_items=len(items),
            country=next(iter(countries)) if len(countries) == 1 else None,
            category="shoes",
            gender=("men" if genders == {"men"} else
                    "women" if genders == {"women"} else
                    "unisex" if genders else "unknown"),
        )

    def brand_url(self, brand: str, items: list[Item]) -> str:
        return items[0].url if items else ""
