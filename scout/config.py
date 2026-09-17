"""config.yaml loading and validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


class HttpConfig(BaseModel):
    user_agent: str = "ScoutBot/0.1 (+https://venexis.example; contact@example.com)"
    request_delay_seconds: float = 2.0     # per host
    timeout_seconds: float = 30.0
    max_retries: int = 4
    backoff_base_seconds: float = 2.0
    respect_robots: bool = True
    cache_ttl_hours: float = 24.0
    max_pages_per_source: int = 20


class SourceConfig(BaseModel):
    """Per-source settings; collectors read their own extra keys."""

    model_config = ConfigDict(extra="allow")

    type: str                      # html | shopify
    enabled: bool = False
    notes: str = ""

    def opt(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default) if hasattr(self, key) else default


class RulesConfig(BaseModel):
    allowed_countries: list[str] = ["IT"]
    price_min: float = 250.0
    price_max: float = 700.0
    price_band_tolerance: float = 0.2   # accept brands whose band overlaps +/- 20%
    min_items: int = 2
    max_items: int = 80
    chronic_discount_pct: float = 40.0
    min_sources: int = 1
    excluded_brands: list[str] = []      # slugs: groups, majors, non-IT
    sneaker_keywords: list[str] = ["sneaker", "trainer", "running"]
    women_keywords: list[str] = ["woman", "women", "donna", "female"]
    men_keywords: list[str] = ["man", "men", "uomo", "male", "mens"]


class ScoringConfig(BaseModel):
    """Weights for the deterministic prescore (0-100)."""

    price_in_band: int = 20
    chronic_discount: int = 25
    few_items: int = 20
    italian: int = 20
    mens: int = 15
    few_items_threshold: int = 30


class ClassifyConfig(BaseModel):
    enabled: bool = True
    backend: str = "ollama"         # ollama | stub (stub = offline, no model needed)
    host: str = "http://localhost:11434"
    model: str = "gemma3:4b"
    temperature: float = 0.0
    timeout_seconds: float = 120.0
    max_retries: int = 3
    min_prescore: int = 30          # skip the LLM below this prescore


class EnrichConfig(BaseModel):
    enabled: bool = True
    backend: str = "claude"          # claude | stub (stub = offline, no API key)
    model: str = "claude-opus-5"
    min_score: int = 70              # only strong candidates reach Claude
    max_per_run: int = 10            # cost guard
    max_tokens: int = 8000
    effort: str = "medium"           # low | medium | high | xhigh | max
    max_searches: int = 6            # web_search max_uses
    refresh_after_days: int = 30     # re-run an existing brief only when this old
    rerun_on_score_delta: float = 15.0   # ...or when the score moved this much
    timeout_seconds: float = 300.0
    api_key_env: str = "ANTHROPIC_API_KEY"


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    api_base: str = "https://api.telegram.org"


class SheetsConfig(BaseModel):
    enabled: bool = False
    spreadsheet_id: str = ""
    credentials_file: str = "credentials/service_account.json"
    candidates_tab: str = "candidati"
    log_tab: str = "log"


class NotifyConfig(BaseModel):
    min_score: int = 70
    score_delta_threshold: float = 15.0
    telegram: TelegramConfig = TelegramConfig()


class Settings(BaseModel):
    db_path: Path = Path("data/scout.db")
    cache_dir: Path = Path("data/cache")
    log_file: Path | None = Path("data/scout.log")
    log_level: str = "INFO"
    http: HttpConfig = HttpConfig()
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    rules: RulesConfig = RulesConfig()
    scoring: ScoringConfig = ScoringConfig()
    classify: ClassifyConfig = ClassifyConfig()
    enrich: EnrichConfig = EnrichConfig()
    notify: NotifyConfig = NotifyConfig()
    sheets: SheetsConfig = SheetsConfig()

    def enabled_sources(self, only: str | None = None) -> dict[str, SourceConfig]:
        if only:
            if only not in self.sources:
                raise KeyError(f"unknown source: {only}")
            return {only: self.sources[only]}
        return {k: v for k, v in self.sources.items() if v.enabled}


def _expand_env(value: Any) -> Any:
    """Replace ${VAR} / ${VAR:-default} in strings, recursively."""
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config(path: str | Path = "config.yaml") -> Settings:
    path = Path(path)
    if not path.exists():
        example = path.with_name("config.example.yaml")
        raise FileNotFoundError(f"{path} not found — copy {example} and edit it")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Settings.model_validate(_expand_env(raw))
