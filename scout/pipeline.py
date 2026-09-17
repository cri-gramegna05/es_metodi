"""Orchestration: collect -> dedupe -> rules -> persist."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .collectors import build_collector
from .config import Settings
from .db import Database
from .dedupe import BrandResolver
from .http import Fetcher
from .log import get_logger
from .models import Observation
from .rules import BrandView, RuleEngine

log = get_logger(__name__)


@dataclass
class RunSummary:
    run_id: int | None = None
    sources: list[str] = field(default_factory=list)
    items: int = 0
    brands_seen: int = 0
    brands_new: int = 0
    passed: int = 0
    dropped: int = 0
    errors: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def as_counters(self) -> dict[str, Any]:
        return {
            "sources": self.sources, "items": self.items, "brands_seen": self.brands_seen,
            "brands_new": self.brands_new, "passed": self.passed, "dropped": self.dropped,
            "errors": self.errors,
        }


class Pipeline:
    def __init__(self, settings: Settings, db: Database, fetcher: Fetcher | None = None) -> None:
        self.settings = settings
        self.db = db
        self.engine = RuleEngine(settings.rules, settings.scoring)
        self._fetcher = fetcher  # injected in tests; otherwise built per run

    def run(self, only_source: str | None = None, dry_run: bool = False) -> RunSummary:
        sources = self.settings.enabled_sources(only_source)
        summary = RunSummary(sources=list(sources))
        if not sources:
            log.warning("no_enabled_sources")
            return summary

        run_id = None if dry_run else self.db.start_run(list(sources))
        summary.run_id = run_id
        known = {slug: name for _, slug, name in self.db.all_brand_slugs()}
        resolver = BrandResolver(known)
        by_brand: dict[str, list[Observation]] = defaultdict(list)
        names: dict[str, str] = {}
        new_slugs: set[str] = set()

        fetcher = self._fetcher or Fetcher(self.settings.http, self.settings.cache_dir)
        try:
            for name, cfg in sources.items():
                try:
                    observations = build_collector(name, cfg, fetcher).collect()
                except Exception as exc:  # one bad source must not kill the run
                    log.error("source_failed", source=name, error=str(exc), exc_info=True)
                    summary.errors.append(f"{name}: {exc}")
                    continue
                for obs in observations:
                    resolution = resolver.resolve(obs.brand)
                    if not resolution.matched_existing and resolution.slug not in known:
                        new_slugs.add(resolution.slug)
                    names[resolution.slug] = resolution.display_name
                    by_brand[resolution.slug].append(obs)
                    summary.items += obs.n_items
                    if not dry_run and run_id is not None:
                        brand_id = self.db.upsert_brand(
                            resolution.slug, resolution.display_name, country=obs.country
                        )
                        self.db.add_alias(brand_id, obs.brand, obs.source)
                        self.db.save_observation(brand_id, run_id, obs.model_dump(mode="json"))
        finally:
            if self._fetcher is None:
                fetcher.close()

        summary.brands_seen = len(by_brand)
        summary.brands_new = len(new_slugs)

        for slug, observations in by_brand.items():
            view = BrandView.build(slug, names[slug], observations)
            result = self.engine.evaluate(view)
            if result.passed:
                summary.passed += 1
                summary.candidates.append({
                    "slug": slug, "brand": names[slug], "prescore": result.prescore,
                    "signals": result.signals, "sources": sorted(view.sources),
                    "price_min": view.price_min, "price_max": view.price_max,
                    "discount_pct": view.discount_pct, "n_items": view.n_items,
                    "is_new": slug in new_slugs,
                })
            else:
                summary.dropped += 1
            if not dry_run and run_id is not None:
                brand_id = self.db.upsert_brand(slug, names[slug])
                self.db.save_rule_result(
                    brand_id, run_id, result.passed, result.prescore,
                    result.reasons, result.signals,
                )
                self.db.set_score(
                    brand_id, result.prescore if result.passed else None,
                    "rules_passed" if result.passed else "rules_dropped",
                )

        summary.candidates.sort(key=lambda c: c["prescore"], reverse=True)
        if not dry_run and run_id is not None:
            self.db.finish_run(
                run_id, summary.as_counters(), status="ok" if not summary.errors else "partial"
            )
        log.info("run_done", **{k: v for k, v in summary.as_counters().items() if k != "errors"})
        return summary
