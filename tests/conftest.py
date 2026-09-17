from __future__ import annotations

from pathlib import Path

import pytest

from scout.config import HttpConfig, RulesConfig, ScoringConfig, SourceConfig
from scout.http import Response

FIXTURES = Path(__file__).parent / "fixtures"
SITE = FIXTURES / "site"


class FakeFetcher:
    """Serves the fixture site from disk; no network, no robots lookups."""

    def __init__(self, root: Path = SITE) -> None:
        self.root = root
        self.requested: list[str] = []

    def get(self, url: str, use_cache: bool = True) -> Response:
        self.requested.append(url)
        path = url.split("://", 1)[-1].split("/", 1)[-1].split("?")[0]
        target = self.root / path
        if not target.exists():
            return Response(url=url, status=404, text="")
        return Response(url=url, status=200, text=target.read_text(encoding="utf-8"))


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def rules_cfg() -> RulesConfig:
    return RulesConfig(excluded_brands=["Tod's", "Golden Goose"])


@pytest.fixture
def scoring_cfg() -> ScoringConfig:
    return ScoringConfig()


@pytest.fixture
def http_cfg() -> HttpConfig:
    return HttpConfig(request_delay_seconds=0, respect_robots=False)


def source(**kwargs) -> SourceConfig:
    return SourceConfig(**kwargs)


class FakeTelegram:
    """Stands in for TelegramNotifier: records what would have been sent."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[str] = []

    def send(self, text: str, max_retries: int = 3) -> bool:
        self.sent.append(text)
        return self.ok


class FakeWorksheet:
    def __init__(self, title: str) -> None:
        self.title = title
        self.rows: list[list] = []

    def get_all_values(self) -> list[list[str]]:
        return [[str(c) for c in row] for row in self.rows]

    def update(self, range_name: str, values: list[list]) -> None:
        index = int(range_name.lstrip("A")) - 1
        while len(self.rows) <= index:
            self.rows.append([])
        self.rows[index] = values[0]

    def append_row(self, values: list) -> None:
        self.rows.append(values)


class FakeSpreadsheet:
    def __init__(self) -> None:
        self.tabs: dict[str, FakeWorksheet] = {}

    def worksheet(self, title: str) -> FakeWorksheet:
        if title not in self.tabs:
            raise KeyError(title)          # gspread raises WorksheetNotFound
        return self.tabs[title]

    def add_worksheet(self, title: str, rows: int = 100, cols: int = 20) -> FakeWorksheet:
        self.tabs[title] = FakeWorksheet(title)
        return self.tabs[title]
