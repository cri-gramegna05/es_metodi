"""Deterministic predicates. Each returns (ok, reason) — reason set only when ok is False."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import RulesConfig
from ..dedupe.normalize import brand_slug

if TYPE_CHECKING:  # pragma: no cover
    from .engine import BrandView

Check = tuple[bool, str | None]


def not_blacklisted(view: "BrandView", cfg: RulesConfig) -> Check:
    # Entries may be written as plain names; compare on slugs.
    if view.slug in {brand_slug(b) for b in cfg.excluded_brands}:
        return False, "blacklisted"
    return True, None


def is_italian(view: "BrandView", cfg: RulesConfig) -> Check:
    """Drop only when every source agrees the brand is foreign; unknown passes to the LLM."""
    known = {c.upper() for c in view.countries if c}
    if known and not known & {c.upper() for c in cfg.allowed_countries}:
        return False, f"country={','.join(sorted(known))}"
    return True, None


def is_mens(view: "BrandView", cfg: RulesConfig) -> Check:
    if view.genders and view.genders <= {"women"}:
        return False, "women-only"
    return True, None


def price_in_band(view: "BrandView", cfg: RulesConfig) -> Check:
    if view.price_min is None or view.price_max is None:
        return True, None  # unknown price: keep, the LLM stage may resolve it
    low = cfg.price_min * (1 - cfg.price_band_tolerance)
    high = cfg.price_max * (1 + cfg.price_band_tolerance)
    if view.price_max < low:
        return False, f"too cheap (max {view.price_max:.0f} < {low:.0f})"
    if view.price_min > high:
        return False, f"too expensive (min {view.price_min:.0f} > {high:.0f})"
    return True, None


def assortment_size(view: "BrandView", cfg: RulesConfig) -> Check:
    if view.n_items > cfg.max_items:
        return False, f"too many items ({view.n_items} > {cfg.max_items})"
    if view.n_items < cfg.min_items:
        return False, f"too few items ({view.n_items} < {cfg.min_items})"
    return True, None


def not_sneaker_first(view: "BrandView", cfg: RulesConfig) -> Check:
    if view.sneaker_share is not None and view.sneaker_share > 0.5:
        return False, f"sneaker-first ({view.sneaker_share:.0%})"
    return True, None


HARD_FILTERS = [
    not_blacklisted,
    is_italian,
    is_mens,
    price_in_band,
    assortment_size,
    not_sneaker_first,
]
