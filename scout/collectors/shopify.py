"""Shopify storefronts: /products.json is a public, stable, robots-checked endpoint.

Most small Italian multibrand boutiques run Shopify, so one collector covers many
sources — add a shop to config.yaml and it is picked up on the next run.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from ..http import RobotsDisallowed
from ..models import Item
from .base import Collector

# Sneakers are matched on purpose: the rules stage needs to see them to drop
# sneaker-first brands, instead of silently missing half their assortment.
SHOE_RE = re.compile(
    r"\b(shoes?|scarp\w*|calzatur\w*|loafers?|mocassin\w*|derby|oxford|boots?|stival\w*|"
    r"sandal\w*|chelsea|monk|brogue|slipper\w*|sneaker\w*)\b",
    re.I,
)


class ShopifyCollector(Collector):
    type = "shopify"

    @property
    def shops(self) -> list[dict[str, Any]]:
        return list(getattr(self.cfg, "shops", None) or [])

    def iter_items(self) -> Iterator[Item]:
        pages = int(getattr(self.cfg, "pages", 3) or 3)
        limit = int(getattr(self.cfg, "page_size", 250) or 250)
        for shop in self.shops:
            domain = shop["domain"].rstrip("/")
            scheme = shop.get("scheme", getattr(self.cfg, "scheme", "https"))
            for handle in shop.get("collections") or [None]:
                path = f"/collections/{handle}/products.json" if handle else "/products.json"
                for page in range(1, pages + 1):
                    url = f"{scheme}://{domain}{path}?limit={limit}&page={page}"
                    products = self._fetch_page(url)
                    if not products:
                        break
                    for product in products:
                        item = self._to_item(product, f"{scheme}://{domain}", shop)
                        if item:
                            yield item

    def _fetch_page(self, url: str) -> list[dict[str, Any]]:
        try:
            resp = self.fetcher.get(url)
        except RobotsDisallowed:
            self.log.warning("robots_disallowed", url=url)
            return []
        except RuntimeError as exc:
            self.log.error("fetch_failed", url=url, error=str(exc))
            return []
        if not resp.ok:
            self.log.warning("page_not_ok", url=url, status=resp.status)
            return []
        try:
            return json.loads(resp.text).get("products", [])
        except json.JSONDecodeError:
            self.log.warning("not_a_shopify_shop", url=url)
            return []

    def _to_item(self, product: dict[str, Any], base: str, shop: dict[str, Any]) -> Item | None:
        vendor = (product.get("vendor") or "").strip()
        if not vendor:
            return None
        haystack = " ".join(
            [product.get("product_type", ""), product.get("title", ""), " ".join(product.get("tags", []) or [])]
        )
        if not SHOE_RE.search(haystack):
            return None

        variants = product.get("variants") or []
        prices = [float(v["price"]) for v in variants if v.get("price")]
        fulls = [float(v["compare_at_price"]) for v in variants if v.get("compare_at_price")]
        if not prices:
            return None
        return Item(
            brand=vendor,
            title=product.get("title", ""),
            url=f"{base}/products/{product.get('handle', '')}",
            price=min(prices),
            full_price=max(fulls) if fulls else None,
            currency=shop.get("currency", getattr(self.cfg, "currency", "EUR")),
            category=product.get("product_type") or "shoes",
            gender=shop.get("gender", getattr(self.cfg, "gender", "unknown")),
            country=shop.get("country", getattr(self.cfg, "country", None)),
        )
