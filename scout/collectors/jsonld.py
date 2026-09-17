"""Extract products from schema.org JSON-LD — the most portable path across shops."""

from __future__ import annotations

import json
from typing import Any, Iterator

from bs4 import BeautifulSoup


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _types(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type", "")
    values = raw if isinstance(raw, list) else [raw]
    return {str(v).lower() for v in values}


def _first_offer(node: dict[str, Any]) -> dict[str, Any]:
    offers = node.get("offers")
    if isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict):
                return offer
        return {}
    return offers if isinstance(offers, dict) else {}


def iter_products(html: str) -> Iterator[dict[str, Any]]:
    """Yield {brand, name, url, price, currency, ...} for every Product in the page."""
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk(data):
            if not isinstance(node, dict) or "product" not in _types(node):
                continue
            brand = node.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            if not brand:
                continue
            offer = _first_offer(node)
            yield {
                "brand": str(brand),
                "name": str(node.get("name", "")),
                "url": str(node.get("url") or offer.get("url") or ""),
                "price": offer.get("price"),
                "full_price": offer.get("highPrice") or node.get("listPrice"),
                "currency": offer.get("priceCurrency") or "EUR",
                "category": str(node.get("category", "")),
            }
