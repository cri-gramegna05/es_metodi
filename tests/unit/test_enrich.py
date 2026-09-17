from types import SimpleNamespace

import pytest

from scout.classify.schema import Classification
from scout.config import EnrichConfig
from scout.enrich import ClaudeEnricher, StubEnricher, parse_revenue
from scout.enrich.claude import WEB_SEARCH_TOOL
from scout.models import Observation
from scout.rules import BrandView

BRIEF = """## Storia
Fondata nel 2016 da un singolo fondatore.

## Stima fatturato
Tra 600k e 800k EUR.

REVENUE_ESTIMATE_EUR: 700000
"""


def view() -> BrandView:
    obs = Observation(
        brand="Edhèn Milano", source="demo", url="https://example.com/p/1",
        price_min=265.0, price_max=330.0, discount_pct=50.0, n_items=6, gender="men",
    )
    return BrandView.build("edhen-milano", "Edhen Milano", [obs])


def classification() -> Classification:
    return Classification(
        is_italian=True, is_mens=True, positioning="premium", founder_type="influencer",
        red_flags=[], score=88, rationale="x",
    )


class FakeMessages:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, *responses) -> None:
        self.messages = FakeMessages(*responses)


def text_block(text: str, citations=None):
    return SimpleNamespace(type="text", text=text, citations=citations)


def search_result_block(urls: list[str]):
    return SimpleNamespace(
        type="web_search_tool_result",
        content=[SimpleNamespace(type="web_search_result", url=u) for u in urls],
    )


@pytest.mark.parametrize("markdown,expected", [
    ("REVENUE_ESTIMATE_EUR: 700000", 700000.0),
    ("REVENUE_ESTIMATE_EUR: 1,250,000", 1250000.0),
    ("REVENUE_ESTIMATE_EUR: unknown", None),
    ("no marker at all", None),
])
def test_parse_revenue(markdown, expected):
    assert parse_revenue(markdown) == expected


def test_request_declares_web_search_and_the_configured_model():
    client = FakeClient(SimpleNamespace(
        content=[search_result_block(["https://edhenmilano.com/about"]), text_block(BRIEF)],
        stop_reason="end_turn",
    ))
    cfg = EnrichConfig(model="claude-opus-5", max_searches=4, effort="medium")
    brief = ClaudeEnricher(cfg, client).enrich(view(), classification())

    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["tools"] == [{"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": 4}]
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"] == {"effort": "medium"}
    assert "Edhen Milano" in call["messages"][0]["content"]

    assert brief.revenue_estimate_eur == 700000.0
    assert brief.sources == ["https://edhenmilano.com/about"]
    assert "## Stima fatturato" in brief.markdown


def test_paused_turn_is_resumed():
    client = FakeClient(
        SimpleNamespace(content=[text_block("partial...")], stop_reason="pause_turn"),
        SimpleNamespace(content=[text_block(BRIEF)], stop_reason="end_turn"),
    )
    brief = ClaudeEnricher(EnrichConfig(), client).enrich(view())
    assert len(client.messages.calls) == 2
    assert brief.revenue_estimate_eur == 700000.0


def test_search_error_block_does_not_crash():
    # Web search failures come back as HTTP 200 with an error object, not a list.
    client = FakeClient(SimpleNamespace(
        content=[
            SimpleNamespace(type="web_search_tool_result",
                            content=SimpleNamespace(error_code="max_uses_exceeded")),
            text_block(BRIEF),
        ],
        stop_reason="end_turn",
    ))
    brief = ClaudeEnricher(EnrichConfig(), client).enrich(view())
    assert brief.sources == [] and brief.revenue_estimate_eur == 700000.0


def test_citations_are_collected_and_deduplicated():
    citation = SimpleNamespace(url="https://pambianconews.com/x")
    client = FakeClient(SimpleNamespace(
        content=[
            search_result_block(["https://pambianconews.com/x", "https://edhen.com"]),
            text_block(BRIEF, citations=[citation]),
        ],
        stop_reason="end_turn",
    ))
    brief = ClaudeEnricher(EnrichConfig(), client).enrich(view())
    assert brief.sources == ["https://pambianconews.com/x", "https://edhen.com"]


def test_missing_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ClaudeEnricher(EnrichConfig())


def test_stub_enricher_produces_every_section():
    brief = StubEnricher(EnrichConfig()).enrich(view(), classification())
    for section in ("## Storia", "## Distribuzione", "## Stima fatturato",
                    "## Segnali di stress", "## Prossimo passo"):
        assert section in brief.markdown
    assert brief.revenue_estimate_eur == parse_revenue(brief.markdown)
