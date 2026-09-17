"""Deep dive with Claude + server-side web search, for the best candidates only."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

from ..classify.schema import Classification
from ..config import EnrichConfig
from ..log import get_logger
from ..rules import BrandView
from .prompts import SYSTEM, user_prompt

log = get_logger(__name__)

REVENUE_RE = re.compile(r"REVENUE_ESTIMATE_EUR:\s*([0-9][0-9_.,]*|unknown)", re.I)
WEB_SEARCH_TOOL = "web_search_20260209"


@dataclass
class Brief:
    markdown: str
    revenue_estimate_eur: float | None
    sources: list[str]
    model: str


class MessagesAPI(Protocol):  # what we need from anthropic.Anthropic
    messages: Any


def parse_revenue(markdown: str) -> float | None:
    match = REVENUE_RE.search(markdown)
    if not match or match.group(1).lower() == "unknown":
        return None
    raw = match.group(1).replace("_", "").replace(",", "").rstrip(".")
    try:
        return float(raw)
    except ValueError:
        return None


def _text_and_sources(content: list[Any]) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    sources: list[str] = []
    for block in content:
        btype = getattr(block, "type", None)
        if btype == "text":
            texts.append(getattr(block, "text", ""))
            for citation in getattr(block, "citations", None) or []:
                url = getattr(citation, "url", None)
                if url:
                    sources.append(url)
        elif btype == "web_search_tool_result":
            results = getattr(block, "content", None)
            # On error the API returns an object here instead of a list (HTTP 200).
            if isinstance(results, list):
                sources += [u for u in (getattr(r, "url", None) for r in results) if u]
            else:
                log.warning("web_search_error",
                            code=getattr(results, "error_code", "unknown"))
    return texts, sources


class ClaudeEnricher:
    """Wraps the Anthropic SDK. `client` is injectable so tests need no network."""

    name = "claude"

    def __init__(self, cfg: EnrichConfig, client: MessagesAPI | None = None) -> None:
        self.cfg = cfg
        self.client = client or self._default_client()

    def _default_client(self) -> MessagesAPI:
        import anthropic  # imported lazily: only needed when enrichment runs

        api_key = os.environ.get(self.cfg.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self.cfg.api_key_env} is not set — needed for enrich.backend=claude"
            )
        return anthropic.Anthropic(api_key=api_key, timeout=self.cfg.timeout_seconds)

    def enrich(self, view: BrandView, classification: Classification | None = None) -> Brief:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt(view, classification)}
        ]
        texts: list[str] = []
        sources: list[str] = []

        # The server may pause a turn between searches; resume until it stops.
        for _ in range(5):
            response = self.client.messages.create(
                model=self.cfg.model,
                max_tokens=self.cfg.max_tokens,
                system=SYSTEM,
                messages=messages,
                tools=[{
                    "type": WEB_SEARCH_TOOL,
                    "name": "web_search",
                    "max_uses": self.cfg.max_searches,
                }],
                thinking={"type": "adaptive"},
                output_config={"effort": self.cfg.effort},
            )
            chunk_texts, chunk_sources = _text_and_sources(response.content)
            texts += chunk_texts
            sources += chunk_sources
            if getattr(response, "stop_reason", None) != "pause_turn":
                if getattr(response, "stop_reason", None) == "refusal":
                    log.warning("enrich_refused", brand=view.slug)
                break
            messages.append({"role": "assistant", "content": response.content})

        markdown = "\n".join(t for t in texts if t).strip()
        return Brief(
            markdown=markdown,
            revenue_estimate_eur=parse_revenue(markdown),
            sources=list(dict.fromkeys(sources)),
            model=self.cfg.model,
        )


class StubEnricher:
    """Offline stand-in: renders a brief from what we already observed."""

    name = "stub"

    def __init__(self, cfg: EnrichConfig) -> None:
        self.cfg = cfg

    def enrich(self, view: BrandView, classification: Classification | None = None) -> Brief:
        price = (
            f"{view.price_min:.0f}-{view.price_max:.0f} EUR"
            if view.price_min is not None else "n/d"
        )
        discount = f"{view.discount_pct:.0f}%" if view.discount_pct is not None else "n/d"
        estimate = 250_000 + 25_000 * view.n_items
        markdown = "\n".join([
            f"# {view.display_name}",
            "",
            "## Storia",
            "_Non verificato: backend stub, nessuna ricerca web eseguita._",
            "",
            "## Fondatori e assetto",
            f"Tipo fondatore ipotizzato: "
            f"{classification.founder_type if classification else 'unknown'}.",
            "",
            "## Prodotto e posizionamento",
            f"Fascia prezzo osservata {price}, posizionamento "
            f"{classification.positioning if classification else 'unknown'}.",
            "",
            "## Distribuzione",
            f"Visto su: {', '.join(sorted(view.sources))} ({view.n_items} item).",
            "",
            "## Stima fatturato",
            f"Stima grezza da assortimento osservato: ~{estimate:,.0f} EUR (bassa confidenza).",
            "",
            "## Segnali di stress",
            f"Sconto medio marketplace {discount}, quota item in saldo "
            f"{view.discounted_share:.0%}." if view.discounted_share is not None
            else f"Sconto medio marketplace {discount}.",
            "",
            "## Perché interessante per Venexis",
            f"Score screening {classification.score if classification else 'n/d'}.",
            "",
            "## Prossimo passo",
            "Verificare bilanci e numero retailer prima di un contatto.",
            "",
            f"REVENUE_ESTIMATE_EUR: {estimate}",
        ])
        return Brief(markdown, float(estimate), [], f"stub:{self.cfg.model}")


def build_enricher(cfg: EnrichConfig, client: MessagesAPI | None = None):
    if cfg.backend == "stub":
        return StubEnricher(cfg)
    if cfg.backend == "claude":
        return ClaudeEnricher(cfg, client)
    raise KeyError(f"unknown enrich backend: {cfg.backend!r} (known: claude, stub)")
