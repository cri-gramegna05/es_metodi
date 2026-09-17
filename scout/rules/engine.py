"""Merges observations into a brand view and applies the deterministic filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from ..config import RulesConfig, ScoringConfig
from ..models import Observation, RuleResult
from .filters import HARD_FILTERS


@dataclass
class BrandView:
    """Everything the rules know about one brand, merged across sources."""

    slug: str
    display_name: str
    observations: list[Observation] = field(default_factory=list)

    @classmethod
    def build(cls, slug: str, display_name: str, observations: list[Observation]) -> "BrandView":
        return cls(slug=slug, display_name=display_name, observations=list(observations))

    @property
    def sources(self) -> set[str]:
        return {o.source for o in self.observations}

    @property
    def countries(self) -> set[str]:
        return {o.country for o in self.observations if o.country}

    @property
    def genders(self) -> set[str]:
        return {o.gender for o in self.observations if o.gender and o.gender != "unknown"}

    @property
    def n_items(self) -> int:
        return sum(o.n_items for o in self.observations)

    @property
    def price_min(self) -> float | None:
        values = [o.price_min for o in self.observations if o.price_min is not None]
        return min(values) if values else None

    @property
    def price_max(self) -> float | None:
        values = [o.price_max for o in self.observations if o.price_max is not None]
        return max(values) if values else None

    @property
    def discount_pct(self) -> float | None:
        """Item-weighted mean discount across sources."""
        pairs = [(o.discount_pct, max(o.n_items, 1)) for o in self.observations
                 if o.discount_pct is not None]
        if not pairs:
            return None
        total = sum(w for _, w in pairs)
        return round(sum(d * w for d, w in pairs) / total, 1)

    @property
    def discounted_share(self) -> float | None:
        values = [o.discounted_share for o in self.observations if o.discounted_share is not None]
        return round(mean(values), 3) if values else None

    @property
    def sneaker_share(self) -> float | None:
        values = [o.sneaker_share for o in self.observations if o.sneaker_share is not None]
        return round(mean(values), 3) if values else None


class RuleEngine:
    def __init__(self, rules: RulesConfig, scoring: ScoringConfig) -> None:
        self.rules = rules
        self.scoring = scoring

    def evaluate(self, view: BrandView) -> RuleResult:
        reasons: list[str] = []
        for check in HARD_FILTERS:
            ok, reason = check(view, self.rules)
            if not ok and reason:
                reasons.append(reason)

        signals = self._signals(view)
        passed = not reasons and len(view.sources) >= self.rules.min_sources
        if not passed and not reasons:
            reasons.append(f"seen on {len(view.sources)} source(s)")
        return RuleResult(
            brand_slug=view.slug,
            passed=passed,
            reasons=reasons,
            signals=[name for name, _ in signals],
            prescore=min(100, sum(points for _, points in signals)) if passed else 0,
        )

    def _signals(self, view: BrandView) -> list[tuple[str, int]]:
        s = self.scoring
        hits: list[tuple[str, int]] = []
        if view.price_min is not None and view.price_max is not None:
            band = range(int(self.rules.price_min), int(self.rules.price_max) + 1)
            if view.price_max >= band.start and view.price_min <= band.stop:
                hits.append(("price_in_band", s.price_in_band))
        if view.discount_pct is not None and view.discount_pct >= self.rules.chronic_discount_pct:
            hits.append(("chronic_discount", s.chronic_discount))
        if 0 < view.n_items <= s.few_items_threshold:
            hits.append(("few_items", s.few_items))
        if any(c.upper() == "IT" for c in view.countries):
            hits.append(("italian", s.italian))
        if "men" in view.genders or "unisex" in view.genders:
            hits.append(("mens", s.mens))
        return hits
