import httpx
import pytest

from scout.config import NotifyConfig, SheetsConfig, TelegramConfig
from scout.publish import (
    SheetsPublisher, TelegramNotifier, candidate_row, decide, format_message, log_row,
)
from scout.publish.sheets import CANDIDATE_HEADER
from tests.conftest import FakeSpreadsheet


def candidate(**kwargs) -> dict:
    base = dict(
        slug="edhen-milano", brand="Edhen Milano", score=88, prescore=80, old_score=None,
        is_new=True, price_min=265.0, price_max=330.0, discount_pct=50.0, n_items=6,
        sources=["farfetch", "yoox"], signals=["chronic_discount"],
        classification={
            "is_italian": True, "is_mens": True, "positioning": "premium",
            "founder_type": "influencer", "red_flags": ["stock scontato"],
            "rationale": "Piccolo brand milanese.", "score": 88,
        },
    )
    return base | kwargs


# --- who gets notified -------------------------------------------------------

def test_new_brand_above_threshold_is_notified():
    [notification] = decide([candidate()], NotifyConfig(min_score=70))
    assert notification.kind == "new" and notification.score == 88


def test_low_score_is_never_notified():
    assert decide([candidate(score=40)], NotifyConfig(min_score=70)) == []


def test_small_score_move_is_ignored():
    assert decide([candidate(score=80, old_score=70, is_new=False)], NotifyConfig()) == []


@pytest.mark.parametrize("new,old,kind", [(90, 70, "score_up"), (72, 95, "score_down")])
def test_big_score_move_is_notified(new, old, kind):
    [notification] = decide([candidate(score=new, old_score=old, is_new=False)],
                            NotifyConfig(score_delta_threshold=15))
    assert notification.kind == kind and str(old) in notification.reason


def test_known_brand_without_a_previous_score_counts_as_new():
    [notification] = decide([candidate(is_new=False, old_score=None)], NotifyConfig())
    assert notification.kind == "new"


def test_message_carries_the_decision_facts():
    c = candidate(revenue_estimate_eur=700000.0)
    [notification] = decide([c], NotifyConfig())
    text = format_message(notification, c)
    assert "Edhen Milano" in text and "88" in text
    assert "265-330 EUR" in text and "50%" in text
    assert "farfetch, yoox" in text and "stock scontato" in text
    assert "700,000" in text


# --- telegram ----------------------------------------------------------------

def notifier(handler, **cfg_kwargs) -> TelegramNotifier:
    config = TelegramConfig(enabled=True, bot_token="t", chat_id="c", **cfg_kwargs)
    return TelegramNotifier(config, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_telegram_posts_to_send_message():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"ok": True})

    assert notifier(handler).send("ciao") is True
    assert seen["url"] == "https://api.telegram.org/bott/sendMessage"
    assert '"chat_id":"c"' in seen["body"].replace(", ", ",")
    assert "Markdown" in seen["body"]


def test_telegram_respects_a_custom_api_base():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("http://127.0.0.1:18080/bot")
        return httpx.Response(200, json={"ok": True})

    assert notifier(handler, api_base="http://127.0.0.1:18080").send("ciao") is True


def test_telegram_gives_up_on_a_client_error():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"ok": False, "description": "chat not found"})

    assert notifier(handler).send("ciao") is False
    assert len(calls) == 1          # retrying a bad chat id is pointless


def test_telegram_is_skipped_when_not_configured():
    disabled = TelegramNotifier(TelegramConfig(enabled=False))
    assert disabled.configured is False and disabled.send("ciao") is False


# --- sheets ------------------------------------------------------------------

def test_candidate_row_matches_the_header():
    row = candidate_row(candidate(), {"first_seen_at": "2026-09-01T10:00:00",
                                      "last_seen_at": "2026-09-17T10:00:00"})
    assert len(row) == len(CANDIDATE_HEADER)
    assert row[0] == "edhen-milano" and row[2] == 88
    assert row[CANDIDATE_HEADER.index("italian")] == "si"
    assert row[CANDIDATE_HEADER.index("first_seen")] == "2026-09-01"


def test_log_row_reports_the_run_counters():
    row = log_row({"sources": ["farfetch"], "items": 120, "passed": 3, "errors": ["boom"]},
                  run_id=7, notified=2)
    assert row[0] == 7 and "farfetch" in row[2] and row[3] == 120 and row[-1] == "boom"


def test_publisher_creates_tabs_and_upserts_by_slug():
    spreadsheet = FakeSpreadsheet()
    publisher = SheetsPublisher(
        SheetsConfig(enabled=True, spreadsheet_id="x"), spreadsheet
    )
    counters = {"sources": ["farfetch"], "items": 10}

    publisher.publish([candidate()], counters, run_id=1, notified=1)
    publisher.publish([candidate(score=91)], counters, run_id=2, notified=0)

    rows = spreadsheet.tabs["candidati"].rows
    assert rows[0] == CANDIDATE_HEADER
    assert len(rows) == 2                     # header + one row for the brand
    assert rows[1][2] == 91                   # updated in place
    assert len(spreadsheet.tabs["log"].rows) == 3


def test_publisher_is_skipped_when_disabled():
    publisher = SheetsPublisher(SheetsConfig(enabled=False), FakeSpreadsheet())
    assert publisher.publish([candidate()], {}, run_id=1, notified=0) == 0
