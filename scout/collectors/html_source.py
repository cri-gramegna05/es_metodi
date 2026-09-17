"""Generic listing-page collector: JSON-LD first, configurable CSS selectors as fallback.

Adding a marketplace usually means adding a block to config.yaml, not a new module.
"""

from __future__ import annotations

from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import RobotsDisallowed
from ..models import Item
from . import jsonld
from .base import Collector, parse_price


class HtmlListingCollector(Collector):
    type = "html"

    # Per-source defaults, overridden by config.
    default_selectors: dict[str, str] = {}
    default_start_urls: list[str] = []

    @property
    def selectors(self) -> dict[str, str]:
        return {**self.default_selectors, **(getattr(self.cfg, "selectors", None) or {})}

    @property
    def start_urls(self) -> list[str]:
        return list(getattr(self.cfg, "start_urls", None) or self.default_start_urls)

    def iter_items(self) -> Iterator[Item]:
        pages = int(getattr(self.cfg, "pages", 1) or 1)
        for template in self.start_urls:
            for page in range(1, pages + 1):
                url = template.format(page=page)
                try:
                    resp = self.fetcher.get(url)
                except RobotsDisallowed:
                    self.log.warning("robots_disallowed", url=url)
                    break
                except RuntimeError as exc:
                    self.log.error("fetch_failed", url=url, error=str(exc))
                    break
                if not resp.ok:
                    self.log.warning("page_not_ok", url=url, status=resp.status)
                    break
                found = list(self.parse(resp.text, url))
                self.log.info("page_parsed", url=url, items=len(found))
                yield from found
                if not found:
                    break  # pagination exhausted

    # --- parsing ----------------------------------------------------------

    def parse(self, html: str, base_url: str) -> Iterator[Item]:
        seen: set[str] = set()
        if getattr(self.cfg, "use_jsonld", True):
            for product in jsonld.iter_products(html):
                item = self._item_from_jsonld(product, base_url)
                if item:
                    seen.add(item.url)
                    yield item
        for item in self._items_from_selectors(html, base_url):
            if item.url not in seen:
                yield item

    def _item_from_jsonld(self, product: dict, base_url: str) -> Item | None:
        price = parse_price(str(product.get("price"))) if product.get("price") else None
        full = parse_price(str(product.get("full_price"))) if product.get("full_price") else None
        try:
            return Item(
                brand=product["brand"],
                title=product.get("name", ""),
                url=urljoin(base_url, product.get("url") or base_url),
                price=price,
                full_price=full,
                currency=product.get("currency") or "EUR",
                category=product.get("category") or "shoes",
                gender=getattr(self.cfg, "gender", "unknown"),
                country=getattr(self.cfg, "country", None),
            )
        except ValueError:
            return None

    def _items_from_selectors(self, html: str, base_url: str) -> Iterator[Item]:
        sel = self.selectors
        if not sel.get("item") or not sel.get("brand"):
            return
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select(sel["item"]):
            brand_el = card.select_one(sel["brand"])
            if not brand_el or not brand_el.get_text(strip=True):
                continue
            link = card.select_one(sel.get("link", "a"))
            href = link.get("href") if link else None
            title_el = card.select_one(sel["title"]) if sel.get("title") else None
            price_el = card.select_one(sel["price"]) if sel.get("price") else None
            full_el = card.select_one(sel["full_price"]) if sel.get("full_price") else None
            try:
                yield Item(
                    brand=brand_el.get_text(strip=True),
                    title=title_el.get_text(strip=True) if title_el else "",
                    url=urljoin(base_url, href) if href else base_url,
                    price=parse_price(price_el.get_text(" ", strip=True)) if price_el else None,
                    full_price=parse_price(full_el.get_text(" ", strip=True)) if full_el else None,
                    currency=getattr(self.cfg, "currency", "EUR"),
                    category=getattr(self.cfg, "category", "shoes"),
                    gender=getattr(self.cfg, "gender", "unknown"),
                    country=getattr(self.cfg, "country", None),
                )
            except ValueError:
                continue
