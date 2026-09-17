"""Google Sheets output: one upserted row per candidate, one appended row per run."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from ..config import SheetsConfig
from ..log import get_logger

log = get_logger(__name__)

CANDIDATE_HEADER = [
    "slug", "brand", "score", "prescore", "old_score", "price_min", "price_max",
    "discount_pct", "n_items", "sources", "italian", "mens", "positioning",
    "founder_type", "red_flags", "rationale", "revenue_estimate_eur", "brief_url",
    "first_seen", "last_seen",
]
LOG_HEADER = [
    "run_id", "finished_at", "sources", "items", "brands_seen", "brands_new",
    "passed", "dropped", "classified", "classify_failed", "enriched", "notified", "errors",
]
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class Worksheet(Protocol):
    def get_all_values(self) -> list[list[str]]: ...
    def update(self, range_name: str, values: list[list[Any]]) -> Any: ...
    def append_row(self, values: list[Any]) -> Any: ...


class Spreadsheet(Protocol):
    def worksheet(self, title: str) -> Worksheet: ...
    def add_worksheet(self, title: str, rows: int, cols: int) -> Worksheet: ...


def candidate_row(candidate: dict[str, Any], brand: dict[str, Any] | None = None) -> list[Any]:
    cls = candidate.get("classification") or {}
    brand = brand or {}
    return [
        candidate["slug"], candidate["brand"], candidate["score"], candidate["prescore"],
        candidate.get("old_score") if candidate.get("old_score") is not None else "",
        candidate.get("price_min") or "", candidate.get("price_max") or "",
        candidate.get("discount_pct") if candidate.get("discount_pct") is not None else "",
        candidate.get("n_items", 0), ", ".join(candidate.get("sources", [])),
        "si" if cls.get("is_italian") else "no" if cls else "",
        "si" if cls.get("is_mens") else "no" if cls else "",
        cls.get("positioning", ""), cls.get("founder_type", ""),
        ", ".join(cls.get("red_flags") or []), cls.get("rationale", ""),
        candidate.get("revenue_estimate_eur") or "",
        candidate.get("brief_url", ""),
        (brand.get("first_seen_at") or "")[:10], (brand.get("last_seen_at") or "")[:10],
    ]


def log_row(counters: dict[str, Any], run_id: int | None, notified: int) -> list[Any]:
    return [
        run_id or "", datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ", ".join(counters.get("sources", [])), counters.get("items", 0),
        counters.get("brands_seen", 0), counters.get("brands_new", 0),
        counters.get("passed", 0), counters.get("dropped", 0),
        counters.get("classified", 0), counters.get("classify_failed", 0),
        counters.get("enriched", 0), notified,
        "; ".join(counters.get("errors", []))[:500],
    ]


class SheetsPublisher:
    """`spreadsheet` is injectable, so tests never touch Google."""

    def __init__(self, cfg: SheetsConfig, spreadsheet: Spreadsheet | None = None) -> None:
        self.cfg = cfg
        self._spreadsheet = spreadsheet

    @property
    def configured(self) -> bool:
        return bool(self.cfg.enabled and self.cfg.spreadsheet_id)

    def _open(self) -> Spreadsheet:
        if self._spreadsheet is not None:
            return self._spreadsheet
        import gspread                                  # lazy: only when publishing
        from google.oauth2.service_account import Credentials

        creds = Credentials.from_service_account_file(self.cfg.credentials_file, scopes=SCOPES)
        self._spreadsheet = gspread.authorize(creds).open_by_key(self.cfg.spreadsheet_id)
        return self._spreadsheet

    def _tab(self, spreadsheet: Spreadsheet, title: str, header: list[str]) -> Worksheet:
        try:
            worksheet = spreadsheet.worksheet(title)
        except Exception:                               # gspread raises WorksheetNotFound
            worksheet = spreadsheet.add_worksheet(title, rows=1000, cols=len(header))
        values = worksheet.get_all_values()
        if not values or values[0] != header:
            worksheet.update("A1", [header])
        return worksheet

    def publish(
        self,
        candidates: list[dict[str, Any]],
        counters: dict[str, Any],
        run_id: int | None,
        notified: int,
        brands: dict[str, dict[str, Any]] | None = None,
    ) -> int:
        """Upsert candidates by slug and append one log row. Returns rows written."""
        if not self.configured:
            log.info("sheets_skipped", reason="not configured")
            return 0
        spreadsheet = self._open()
        tab = self._tab(spreadsheet, self.cfg.candidates_tab, CANDIDATE_HEADER)
        existing = tab.get_all_values()
        row_by_slug = {row[0]: index + 1 for index, row in enumerate(existing) if row and row[0]}

        written = 0
        for candidate in candidates:
            row = candidate_row(candidate, (brands or {}).get(candidate["slug"]))
            line = row_by_slug.get(candidate["slug"])
            if line and line > 1:
                tab.update(f"A{line}", [row])           # same brand, same row: no duplicates
            else:
                tab.append_row(row)
            written += 1

        self._tab(spreadsheet, self.cfg.log_tab, LOG_HEADER).append_row(
            log_row(counters, run_id, notified)
        )
        log.info("sheets_published", rows=written)
        return written
