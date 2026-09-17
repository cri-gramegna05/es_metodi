"""End-to-end collect -> dedupe -> rules -> SQLite, against fixtures."""

from __future__ import annotations

from scout.config import RulesConfig, ScoringConfig, Settings, SourceConfig
from scout.db import Database
from scout.pipeline import Pipeline
from tests.integration.test_collectors import HTML_SOURCE

SHOPIFY_SOURCE = dict(
    type="shopify", enabled=True, pages=1, gender="men", scheme="http",
    shops=[{"domain": "fixture", "collections": ["uomo-scarpe"]}],
)


def make_settings(tmp_path) -> Settings:
    return Settings(
        db_path=tmp_path / "scout.db",
        cache_dir=tmp_path / "cache",
        log_file=None,
        sources={
            "demo_marketplace": SourceConfig(**HTML_SOURCE),
            "demo_shopify": SourceConfig(**SHOPIFY_SOURCE),
        },
        rules=RulesConfig(excluded_brands=["Tod's", "Golden Goose", "Church's"]),
        scoring=ScoringConfig(),
    )


def run_pipeline(tmp_path, fetcher, db=None):
    settings = make_settings(tmp_path)
    db = db or Database(settings.db_path)
    return Pipeline(settings, db, fetcher=fetcher).run(), db


def test_full_run_selects_the_small_italian_brands(tmp_path, fetcher):
    summary, db = run_pipeline(tmp_path, fetcher)
    names = {c["brand"] for c in summary.candidates}
    assert "Edhen Milano" in names
    assert "Tod's" not in names            # blacklisted group
    assert "Autry" not in names            # sneaker-first and below the price band
    assert summary.candidates[0]["brand"] == "Edhen Milano"   # best prescore
    assert summary.brands_new == summary.brands_seen
    db.close()


def test_brand_is_merged_across_sources(tmp_path, fetcher):
    summary, db = run_pipeline(tmp_path, fetcher)
    edhen = next(c for c in summary.candidates if c["brand"] == "Edhen Milano")
    assert set(edhen["sources"]) == {"demo_marketplace", "demo_shopify"}
    assert edhen["n_items"] == 6           # 4 from the listing + 2 from Shopify
    row = db.get_brand_by_slug("edhen-milano")
    assert len(db.latest_observations(row["id"])) == 2
    db.close()


def test_second_run_updates_instead_of_duplicating(tmp_path, fetcher):
    first, db = run_pipeline(tmp_path, fetcher)
    after_first = db.stats()["observations"]
    second, _ = run_pipeline(tmp_path, fetcher, db=db)
    assert second.brands_new == 0
    assert second.brands_seen == first.brands_seen
    assert db.stats()["brands"] == first.brands_seen
    # One row per brand/source/run: two runs double the observations, not the brands.
    assert db.stats()["observations"] == 2 * after_first
    db.close()


def test_run_is_recorded(tmp_path, fetcher):
    summary, db = run_pipeline(tmp_path, fetcher)
    run = db.conn.execute("SELECT * FROM runs WHERE id=?", (summary.run_id,)).fetchone()
    assert run["status"] == "ok" and run["finished_at"]
    db.close()


def test_dry_run_writes_nothing(tmp_path, fetcher):
    settings = make_settings(tmp_path)
    db = Database(settings.db_path)
    summary = Pipeline(settings, db, fetcher=fetcher).run(dry_run=True)
    assert summary.candidates and db.stats()["brands"] == 0
    db.close()
