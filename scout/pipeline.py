"""Orchestration: collect -> dedupe -> rules -> classify (-> enrich -> publish)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .classify import Classification, Classifier
from .collectors import build_collector
from .config import Settings
from .db import Database
from .dedupe import BrandResolver
from .enrich import build_enricher
from .http import Fetcher
from .log import get_logger
from .models import Observation, RuleResult
from .publish import SheetsPublisher, TelegramNotifier, decide, format_message
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
    classified: int = 0
    classify_failed: int = 0
    enriched: int = 0
    notified: int = 0
    sheet_rows: int = 0
    errors: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def as_counters(self) -> dict[str, Any]:
        return {
            "sources": self.sources, "items": self.items, "brands_seen": self.brands_seen,
            "brands_new": self.brands_new, "passed": self.passed, "dropped": self.dropped,
            "classified": self.classified, "classify_failed": self.classify_failed,
            "enriched": self.enriched, "notified": self.notified,
            "sheet_rows": self.sheet_rows, "errors": self.errors,
        }


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        fetcher: Fetcher | None = None,
        classifier: Classifier | None = None,
        enricher: Any = None,
        notifier: TelegramNotifier | None = None,
        sheets: SheetsPublisher | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.engine = RuleEngine(settings.rules, settings.scoring)
        self._fetcher = fetcher        # injected in tests; otherwise built per run
        self._classifier = classifier
        self._enricher = enricher
        self._notifier = notifier
        self._sheets = sheets

    # --- stages -----------------------------------------------------------

    def collect(
        self, sources: dict[str, Any], summary: RunSummary, resolver: BrandResolver,
        run_id: int | None, dry_run: bool,
    ) -> tuple[dict[str, list[Observation]], dict[str, str], set[str]]:
        by_brand: dict[str, list[Observation]] = defaultdict(list)
        names: dict[str, str] = {}
        new_slugs: set[str] = set()
        known = set(resolver.known)

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
        return by_brand, names, new_slugs

    def apply_rules(
        self, views: list[BrandView], summary: RunSummary, run_id: int | None, dry_run: bool
    ) -> list[tuple[BrandView, RuleResult]]:
        passed: list[tuple[BrandView, RuleResult]] = []
        for view in views:
            result = self.engine.evaluate(view)
            if result.passed:
                summary.passed += 1
                passed.append((view, result))
            else:
                summary.dropped += 1
            if not dry_run and run_id is not None:
                brand_id = self.db.upsert_brand(view.slug, view.display_name)
                self.db.save_rule_result(
                    brand_id, run_id, result.passed, result.prescore,
                    result.reasons, result.signals,
                )
                self.db.set_score(
                    brand_id, result.prescore if result.passed else None,
                    "rules_passed" if result.passed else "rules_dropped",
                )
        return passed

    def classify(
        self, passed: list[tuple[BrandView, RuleResult]], summary: RunSummary,
        run_id: int | None, dry_run: bool,
    ) -> dict[str, Classification]:
        cfg = self.settings.classify
        out: dict[str, Classification] = {}
        if not cfg.enabled or not passed:
            return out
        classifier = self._classifier or Classifier(cfg)
        for view, result in passed:
            if result.prescore < cfg.min_prescore:
                log.debug("classify_skipped", brand=view.slug, prescore=result.prescore)
                continue
            try:
                classification = classifier.classify(view)
            except Exception as exc:
                summary.classify_failed += 1
                log.error("classify_failed", brand=view.slug, error=str(exc)[:200])
                continue
            summary.classified += 1
            out[view.slug] = classification
            log.info("classified", brand=view.slug, score=classification.score)
            if not dry_run and run_id is not None:
                brand_id = self.db.upsert_brand(view.slug, view.display_name)
                self.db.save_classification(
                    brand_id, run_id, cfg.model if cfg.backend == "ollama" else cfg.backend,
                    classification.model_dump(),
                )
                self.db.set_score(brand_id, classification.score, "classified")
        return out

    def enrich(
        self, candidates: list[dict[str, Any]], views: dict[str, BrandView],
        summary: RunSummary, run_id: int | None, dry_run: bool,
    ) -> None:
        """Deep dive on the strongest candidates only — this is the paid stage."""
        cfg = self.settings.enrich
        if not cfg.enabled:
            return
        shortlist = [c for c in candidates if c["score"] >= cfg.min_score][: cfg.max_per_run]
        if not shortlist:
            return
        try:
            enricher = self._enricher or build_enricher(cfg)
        except Exception as exc:
            log.error("enrich_unavailable", error=str(exc))
            summary.errors.append(f"enrich: {exc}")
            return

        for candidate in shortlist:
            view = views[candidate["slug"]]
            if not dry_run and self._brief_is_current(candidate, cfg):
                log.debug("enrich_skipped", brand=view.slug, reason="brief still current")
                continue
            classification = candidate.get("classification")
            try:
                brief = enricher.enrich(
                    view,
                    Classification.model_validate(classification) if classification else None,
                )
            except Exception as exc:
                log.error("enrich_failed", brand=view.slug, error=str(exc)[:200])
                summary.errors.append(f"enrich {view.slug}: {str(exc)[:120]}")
                continue
            summary.enriched += 1
            candidate["revenue_estimate_eur"] = brief.revenue_estimate_eur
            candidate["brief_markdown"] = brief.markdown
            candidate["brief_sources"] = brief.sources
            log.info("enriched", brand=view.slug, revenue=brief.revenue_estimate_eur)
            if not dry_run and run_id is not None:
                brand_id = self.db.upsert_brand(view.slug, view.display_name)
                self.db.save_enrichment(brand_id, run_id, brief.model, brief.markdown,
                                        brief.revenue_estimate_eur, brief.sources)
                self.db.set_score(brand_id, candidate["score"], "enriched")

    def _brief_is_current(self, candidate: dict[str, Any], cfg: Any) -> bool:
        """Don't pay for a second brief unless it is stale or the score moved."""
        row = self.db.get_brand_by_slug(candidate["slug"])
        if row is None:
            return False
        age = self.db.enrichment_age_days(row["id"])
        if age is None:
            return False
        old = candidate.get("old_score")
        moved = old is not None and abs(candidate["score"] - old) >= cfg.rerun_on_score_delta
        return age < cfg.refresh_after_days and not moved

    def publish(
        self, candidates: list[dict[str, Any]], summary: RunSummary,
        run_id: int | None, dry_run: bool,
    ) -> None:
        notifier = self._notifier or TelegramNotifier(self.settings.notify.telegram)
        by_slug = {c["slug"]: c for c in candidates}
        for notification in decide(candidates, self.settings.notify):
            candidate = by_slug[notification.slug]
            brand_id = None
            if not dry_run and run_id is not None:
                brand_id = self.db.upsert_brand(notification.slug, notification.brand)
                if self.db.already_notified(brand_id, run_id, "telegram"):
                    continue
            if notifier.send(format_message(notification, candidate)):
                summary.notified += 1
                log.info("notified", brand=notification.slug, kind=notification.kind)
                if brand_id is not None:
                    self.db.record_notification(
                        brand_id, run_id, "telegram", notification.kind,
                        notification.old_score, notification.score,
                    )

        sheets = self._sheets or SheetsPublisher(self.settings.sheets)
        brands = {}
        if not dry_run:
            for candidate in candidates:
                row = self.db.get_brand_by_slug(candidate["slug"])
                if row:
                    brands[candidate["slug"]] = dict(row)
        try:
            summary.sheet_rows = sheets.publish(
                candidates, summary.as_counters(), run_id, summary.notified, brands
            )
        except Exception as exc:
            log.error("sheets_failed", error=str(exc)[:200])
            summary.errors.append(f"sheets: {str(exc)[:120]}")

    # --- driver -----------------------------------------------------------

    def run(self, only_source: str | None = None, dry_run: bool = False) -> RunSummary:
        sources = self.settings.enabled_sources(only_source)
        summary = RunSummary(sources=list(sources))
        if not sources:
            log.warning("no_enabled_sources")
            return summary

        run_id = None if dry_run else self.db.start_run(list(sources))
        summary.run_id = run_id
        previous_scores = self.db.current_scores()
        resolver = BrandResolver({slug: name for _, slug, name in self.db.all_brand_slugs()})

        by_brand, names, new_slugs = self.collect(sources, summary, resolver, run_id, dry_run)
        summary.brands_seen = len(by_brand)
        summary.brands_new = len(new_slugs)

        views = [BrandView.build(slug, names[slug], obs) for slug, obs in by_brand.items()]
        passed = self.apply_rules(views, summary, run_id, dry_run)
        classifications = self.classify(passed, summary, run_id, dry_run)

        for view, result in passed:
            classification = classifications.get(view.slug)
            summary.candidates.append({
                "slug": view.slug, "brand": view.display_name,
                "prescore": result.prescore,
                "score": classification.score if classification else result.prescore,
                "old_score": previous_scores.get(view.slug),
                "is_new": view.slug in new_slugs,
                "signals": result.signals, "sources": sorted(view.sources),
                "price_min": view.price_min, "price_max": view.price_max,
                "discount_pct": view.discount_pct, "n_items": view.n_items,
                "classification": classification.model_dump() if classification else None,
            })
        summary.candidates.sort(key=lambda c: c["score"], reverse=True)

        self.enrich(summary.candidates, {v.slug: v for v, _ in passed}, summary, run_id, dry_run)
        self.publish(summary.candidates, summary, run_id, dry_run)

        if not dry_run and run_id is not None:
            self.db.finish_run(
                run_id, summary.as_counters(), status="ok" if not summary.errors else "partial"
            )
        log.info("run_done", **{k: v for k, v in summary.as_counters().items() if k != "errors"})
        return summary
