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
