"""End-to-end collect -> dedupe -> rules -> SQLite, against fixtures."""

from __future__ import annotations

from scout.config import (
    ClassifyConfig, EnrichConfig, NotifyConfig, RulesConfig, ScoringConfig, Settings,
    SheetsConfig, SourceConfig, TelegramConfig,
)
from scout.db import Database
from scout.pipeline import Pipeline
from scout.publish import SheetsPublisher
from tests.conftest import FakeSpreadsheet, FakeTelegram
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
        classify=ClassifyConfig(backend="stub"),
        enrich=EnrichConfig(backend="stub", min_score=70),
        notify=NotifyConfig(min_score=70, telegram=TelegramConfig(enabled=True,
                                                                  bot_token="t", chat_id="c")),
        sheets=SheetsConfig(enabled=True, spreadsheet_id="sheet-1"),
    )


def run_pipeline(tmp_path, fetcher, db=None, telegram=None, spreadsheet=None):
    settings = make_settings(tmp_path)
    db = db or Database(settings.db_path)
    pipeline = Pipeline(
        settings, db, fetcher=fetcher,
        notifier=telegram or FakeTelegram(),
        sheets=SheetsPublisher(settings.sheets, spreadsheet or FakeSpreadsheet()),
    )
    return pipeline.run(), db


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
    assert run["status"] == "ok" and run["finished_at"], summary.errors
    db.close()


def test_classification_and_enrichment_are_stored(tmp_path, fetcher):
    summary, db = run_pipeline(tmp_path, fetcher)
    assert summary.classified == summary.passed
    best = summary.candidates[0]
    assert best["score"] >= 70 and summary.enriched >= 1
    row = db.get_brand_by_slug(best["slug"])
    assert db.latest_classification(row["id"])["score"] == best["score"]
    brief = db.latest_enrichment(row["id"])
    assert "## Stima fatturato" in brief["markdown"]
    assert brief["revenue_estimate_eur"] > 0
    assert row["current_stage"] == "enriched"
    db.close()


def test_only_new_or_moved_brands_are_notified(tmp_path, fetcher):
    first_telegram = FakeTelegram()
    first, db = run_pipeline(tmp_path, fetcher, telegram=first_telegram)
    notified_first = first.notified
    assert notified_first >= 1
    assert any("Nuovo candidato" in m for m in first_telegram.sent)

    # Same fixtures, same scores: nothing new to say.
    second_telegram = FakeTelegram()
    second, _ = run_pipeline(tmp_path, fetcher, db=db, telegram=second_telegram)
    assert second.notified == 0 and second_telegram.sent == []
    db.close()


def test_sheet_upserts_instead_of_appending(tmp_path, fetcher):
    spreadsheet = FakeSpreadsheet()
    first, db = run_pipeline(tmp_path, fetcher, spreadsheet=spreadsheet)
    run_pipeline(tmp_path, fetcher, db=db, spreadsheet=spreadsheet)
    candidates_tab = spreadsheet.tabs["candidati"]
    slugs = [row[0] for row in candidates_tab.rows[1:]]
    assert len(slugs) == len(set(slugs)) == first.passed   # one row per brand, both runs
    assert len(spreadsheet.tabs["log"].rows) == 3          # header + one row per run
    db.close()


def test_dry_run_writes_nothing(tmp_path, fetcher):
    settings = make_settings(tmp_path)
    db = Database(settings.db_path)
    spreadsheet = FakeSpreadsheet()
    summary = Pipeline(
        settings, db, fetcher=fetcher, notifier=FakeTelegram(),
        sheets=SheetsPublisher(settings.sheets, spreadsheet),
    ).run(dry_run=True)
    assert summary.candidates and db.stats()["brands"] == 0
    assert db.conn.execute("SELECT COUNT(*) c FROM notifications").fetchone()["c"] == 0


def test_brief_is_not_regenerated_on_every_run(tmp_path, fetcher):
    first, db = run_pipeline(tmp_path, fetcher)
    assert first.enriched >= 1
    second, _ = run_pipeline(tmp_path, fetcher, db=db)
    # Same score, fresh brief: no second call to the (paid) enrichment backend.
    assert second.enriched == 0
    best = second.candidates[0]
    row = db.get_brand_by_slug(best["slug"])
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM enrichments WHERE brand_id=?", (row["id"],)
    ).fetchone()["c"] == 1
    db.close()
