"""Telegram Bot API notifications."""

from __future__ import annotations

import time

import httpx

from ..config import TelegramConfig
from ..log import get_logger

log = get_logger(__name__)
API_BASE = "https://api.telegram.org"


class TelegramNotifier:
    def __init__(
        self, cfg: TelegramConfig, client: httpx.Client | None = None,
        api_base: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.api_base = (api_base or cfg.api_base or API_BASE).rstrip("/")
        self.client = client or httpx.Client(timeout=20.0)

    @property
    def configured(self) -> bool:
        return bool(self.cfg.enabled and self.cfg.bot_token and self.cfg.chat_id)

    def send(self, text: str, max_retries: int = 3) -> bool:
        if not self.configured:
            log.info("telegram_skipped", reason="not configured")
            return False
        url = f"{self.api_base}/bot{self.cfg.bot_token}/sendMessage"
        payload = {
            "chat_id": self.cfg.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.client.post(url, json=payload)
            except httpx.HTTPError as exc:
                log.warning("telegram_error", attempt=attempt, error=str(exc))
            else:
                if resp.status_code == 200:
                    return True
                if resp.status_code == 429:
                    # Telegram tells us how long to wait.
                    wait = float(
                        (resp.json().get("parameters") or {}).get("retry_after", 2 ** attempt)
                    )
                    log.warning("telegram_rate_limited", wait=wait)
                    time.sleep(wait)
                    continue
                log.error("telegram_failed", status=resp.status_code, body=resp.text[:200])
                if 400 <= resp.status_code < 500:
                    return False           # bad token or chat id: retrying won't help
            time.sleep(2 ** attempt)
        return False
