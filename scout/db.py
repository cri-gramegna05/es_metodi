"""SQLite storage: schema, migrations and idempotent upserts."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    sources_json TEXT,
    counters_json TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    website TEXT,
    country TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    current_score INTEGER,
    current_stage TEXT NOT NULL DEFAULT 'collected',
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS brand_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    source TEXT NOT NULL,
    UNIQUE(alias, source)
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES runs(id),
    source TEXT NOT NULL,
    url TEXT,
    price_min REAL,
    price_max REAL,
    currency TEXT,
    discount_pct REAL,
    discounted_share REAL,
    sneaker_share REAL,
    n_items INTEGER,
    category TEXT,
    gender TEXT,
    country TEXT,
    raw_json TEXT,
    collected_at TEXT NOT NULL,
    UNIQUE(brand_id, source, run_id)
);

CREATE TABLE IF NOT EXISTS rule_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES runs(id),
    passed INTEGER NOT NULL,
    prescore INTEGER,
    reasons_json TEXT,
    signals_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(brand_id, run_id)
);

CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES runs(id),
    model TEXT,
    is_italian INTEGER,
    is_mens INTEGER,
    positioning TEXT,
    founder_type TEXT,
    red_flags_json TEXT,
    score INTEGER,
    rationale TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enrichments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES runs(id),
    model TEXT,
    markdown TEXT,
    revenue_estimate_eur REAL,
    sources_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES runs(id),
    channel TEXT NOT NULL,
    kind TEXT NOT NULL,
    old_score INTEGER,
    new_score INTEGER,
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS http_cache (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    status INTEGER,
    body_path TEXT,
    etag TEXT
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE INDEX IF NOT EXISTS idx_obs_brand ON observations(brand_id);
CREATE INDEX IF NOT EXISTS idx_obs_run ON observations(run_id);
CREATE INDEX IF NOT EXISTS idx_cls_brand ON classifications(brand_id);
CREATE INDEX IF NOT EXISTS idx_brands_score ON brands(current_score);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    def migrate(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # --- runs -------------------------------------------------------------

    def start_run(self, sources: list[str]) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(started_at, status, sources_json) VALUES(?, 'running', ?)",
            (utcnow_iso(), json.dumps(sources)),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(
        self, run_id: int, counters: dict[str, Any], status: str = "ok", error: str | None = None
    ) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, counters_json=?, error=? WHERE id=?",
            (utcnow_iso(), status, json.dumps(counters), error, run_id),
        )
        self.conn.commit()

    # --- brands -----------------------------------------------------------

    def get_brand_by_slug(self, slug: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM brands WHERE slug = ?", (slug,)).fetchone()

    def all_brand_slugs(self) -> list[tuple[int, str, str]]:
        rows = self.conn.execute("SELECT id, slug, display_name FROM brands").fetchall()
        return [(r["id"], r["slug"], r["display_name"]) for r in rows]

    def upsert_brand(
        self,
        slug: str,
        display_name: str,
        country: str | None = None,
        website: str | None = None,
    ) -> int:
        """Insert or touch a brand; never duplicates on slug."""
        now = utcnow_iso()
        row = self.get_brand_by_slug(slug)
        if row is None:
            cur = self.conn.execute(
                "INSERT INTO brands(slug, display_name, website, country, first_seen_at, last_seen_at) "
                "VALUES(?,?,?,?,?,?)",
                (slug, display_name, website, country, now, now),
            )
            self.conn.commit()
            return int(cur.lastrowid)
        self.conn.execute(
            "UPDATE brands SET last_seen_at=?, country=COALESCE(country, ?), "
            "website=COALESCE(website, ?) WHERE id=?",
            (now, country, website, row["id"]),
        )
        self.conn.commit()
        return int(row["id"])

    def add_alias(self, brand_id: int, alias: str, source: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO brand_aliases(brand_id, alias, source) VALUES(?,?,?)",
            (brand_id, alias, source),
        )
        self.conn.commit()

    def find_brand_id_by_alias(self, alias: str) -> int | None:
        row = self.conn.execute(
            "SELECT brand_id FROM brand_aliases WHERE alias = ? LIMIT 1", (alias,)
        ).fetchone()
        return int(row["brand_id"]) if row else None

    def current_scores(self) -> dict[str, int | None]:
        return {r["slug"]: r["current_score"]
                for r in self.conn.execute("SELECT slug, current_score FROM brands")}

    def set_score(self, brand_id: int, score: int | None, stage: str) -> None:
        self.conn.execute(
            "UPDATE brands SET current_score=?, current_stage=? WHERE id=?",
            (score, stage, brand_id),
        )
        self.conn.commit()

    # --- observations / rules --------------------------------------------

    def save_observation(self, brand_id: int, run_id: int, obs: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO observations(brand_id, run_id, source, url, price_min, price_max,
                   currency, discount_pct, discounted_share, sneaker_share, n_items,
                   category, gender, country, raw_json, collected_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(brand_id, source, run_id) DO UPDATE SET
                   url=excluded.url, price_min=excluded.price_min, price_max=excluded.price_max,
                   discount_pct=excluded.discount_pct, discounted_share=excluded.discounted_share,
                   sneaker_share=excluded.sneaker_share, n_items=excluded.n_items, category=excluded.category, gender=excluded.gender,
                   country=excluded.country, raw_json=excluded.raw_json,
                   collected_at=excluded.collected_at""",
            (
                brand_id, run_id, obs["source"], obs.get("url"), obs.get("price_min"),
                obs.get("price_max"), obs.get("currency", "EUR"), obs.get("discount_pct"),
                obs.get("discounted_share"), obs.get("sneaker_share"), obs.get("n_items", 0),
                obs.get("category"),
                obs.get("gender"), obs.get("country"), json.dumps(obs, default=str),
                obs.get("collected_at", utcnow_iso()),
            ),
        )
        self.conn.commit()

    def latest_observations(self, brand_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT * FROM observations o
               WHERE o.brand_id = ? AND o.collected_at = (
                   SELECT MAX(collected_at) FROM observations
                   WHERE brand_id = o.brand_id AND source = o.source)
               ORDER BY source""",
            (brand_id,),
        ).fetchall()

    def save_rule_result(
        self, brand_id: int, run_id: int, passed: bool, prescore: int,
        reasons: list[str], signals: list[str],
    ) -> None:
        self.conn.execute(
            """INSERT INTO rule_results(brand_id, run_id, passed, prescore, reasons_json,
                   signals_json, created_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(brand_id, run_id) DO UPDATE SET
                   passed=excluded.passed, prescore=excluded.prescore,
                   reasons_json=excluded.reasons_json, signals_json=excluded.signals_json""",
            (brand_id, run_id, int(passed), prescore, json.dumps(reasons),
             json.dumps(signals), utcnow_iso()),
        )
        self.conn.commit()

    # --- classifications --------------------------------------------------

    def save_classification(
        self, brand_id: int, run_id: int, model: str, data: dict[str, Any]
    ) -> None:
        self.conn.execute(
            """INSERT INTO classifications(brand_id, run_id, model, is_italian, is_mens,
                   positioning, founder_type, red_flags_json, score, rationale, raw_json,
                   created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (brand_id, run_id, model, int(bool(data.get("is_italian"))),
             int(bool(data.get("is_mens"))), data.get("positioning"), data.get("founder_type"),
             json.dumps(data.get("red_flags", [])), data.get("score"), data.get("rationale"),
             json.dumps(data, default=str), utcnow_iso()),
        )
        self.conn.commit()

    def latest_classification(self, brand_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM classifications WHERE brand_id=? ORDER BY id DESC LIMIT 1",
            (brand_id,),
        ).fetchone()

    # --- enrichments / notifications --------------------------------------

    def save_enrichment(
        self, brand_id: int, run_id: int, model: str, markdown: str,
        revenue_estimate_eur: float | None, sources: list[str],
    ) -> None:
        self.conn.execute(
            """INSERT INTO enrichments(brand_id, run_id, model, markdown,
                   revenue_estimate_eur, sources_json, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (brand_id, run_id, model, markdown, revenue_estimate_eur,
             json.dumps(sources), utcnow_iso()),
        )
        self.conn.commit()

    def latest_enrichment(self, brand_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM enrichments WHERE brand_id=? ORDER BY id DESC LIMIT 1", (brand_id,)
        ).fetchone()

    def enrichment_age_days(self, brand_id: int) -> float | None:
        row = self.latest_enrichment(brand_id)
        if row is None:
            return None
        created = datetime.fromisoformat(row["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created).total_seconds() / 86400

    def record_notification(
        self, brand_id: int, run_id: int, channel: str, kind: str,
        old_score: int | None, new_score: int | None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO notifications(brand_id, run_id, channel, kind, old_score,
                   new_score, sent_at) VALUES(?,?,?,?,?,?,?)""",
            (brand_id, run_id, channel, kind, old_score, new_score, utcnow_iso()),
        )
        self.conn.commit()

    def already_notified(self, brand_id: int, run_id: int, channel: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM notifications WHERE brand_id=? AND run_id=? AND channel=? LIMIT 1",
            (brand_id, run_id, channel),
        ).fetchone()
        return row is not None

    def brand_row(self, brand_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM brands WHERE id=?", (brand_id,)).fetchone()

    # --- stats ------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        q = self.conn.execute
        out: dict[str, Any] = {
            "brands": q("SELECT COUNT(*) c FROM brands").fetchone()["c"],
            "observations": q("SELECT COUNT(*) c FROM observations").fetchone()["c"],
            "runs": q("SELECT COUNT(*) c FROM runs").fetchone()["c"],
            "passed_last_run": 0,
            "by_source": {},
            "top": [],
        }
        last = q("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if last:
            out["last_run_id"] = last["id"]
            out["passed_last_run"] = q(
                "SELECT COUNT(*) c FROM rule_results WHERE run_id=? AND passed=1", (last["id"],)
            ).fetchone()["c"]
        for r in q("SELECT source, COUNT(DISTINCT brand_id) c FROM observations GROUP BY source"):
            out["by_source"][r["source"]] = r["c"]
        out["top"] = [
            dict(r) for r in q(
                "SELECT display_name, slug, current_score, current_stage FROM brands "
                "WHERE current_score IS NOT NULL ORDER BY current_score DESC LIMIT 10"
            )
        ]
        return out
