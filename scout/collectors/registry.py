"""Maps config source types to collector classes."""

from __future__ import annotations

from ..config import SourceConfig
from ..http import Fetcher
from .base import Collector
from .html_source import HtmlListingCollector
from .shopify import ShopifyCollector
from .sites import FarfetchCollector, GiglioCollector, YooxCollector

COLLECTOR_TYPES: dict[str, type[Collector]] = {
    "html": HtmlListingCollector,
    "shopify": ShopifyCollector,
    "farfetch": FarfetchCollector,
    "yoox": YooxCollector,
    "giglio": GiglioCollector,
}


def build_collector(name: str, cfg: SourceConfig, fetcher: Fetcher) -> Collector:
    try:
        cls = COLLECTOR_TYPES[cfg.type]
    except KeyError as exc:
        raise KeyError(
            f"source {name!r}: unknown type {cfg.type!r} "
            f"(known: {', '.join(sorted(COLLECTOR_TYPES))})"
        ) from exc
    return cls(name, cfg, fetcher)
