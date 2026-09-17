"""Collectors parsed against saved fixtures — no network."""

from __future__ import annotations

from scout.collectors.html_source import HtmlListingCollector
from scout.collectors.shopify import ShopifyCollector
from tests.conftest import source

HTML_SOURCE = dict(
    type="html",
    enabled=True,
    pages=3,
    gender="men",
    start_urls=["http://fixture/uomo-scarpe-{page}.html"],
    selectors={
        "item": "li.product-item",
        "brand": ".product-brand",
        "title": ".product-name",
        "price": ".special-price .price",
        "full_price": ".old-price .price",
        "link": "a.product-item-link",
    },
)


def test_html_collector_reads_both_pages_and_stops(fetcher):
    collector = HtmlListingCollector("demo", source(**HTML_SOURCE), fetcher)
    items = list(collector.iter_items())
    assert len(items) == 18
    # Page 3 is empty, so pagination stops there and page 4 is never requested.
    assert fetcher.requested[-1].endswith("uomo-scarpe-3.html")


def test_html_collector_prefers_jsonld_and_does_not_double_count(fetcher):
    collector = HtmlListingCollector("demo", source(**HTML_SOURCE), fetcher)
    items = [i for i in collector.iter_items() if i.brand.startswith("Edh")]
    assert len(items) == 4
    assert {i.currency for i in items} == {"EUR"}


def test_html_collector_aggregates_prices_and_discounts(fetcher):
    collector = HtmlListingCollector("demo", source(**HTML_SOURCE), fetcher)
    by_brand = {o.brand: o for o in collector.collect()}
    edhen = by_brand["Edhèn Milano"]
    assert edhen.n_items == 4
    assert edhen.price_min == 265.0 and edhen.price_max == 330.0
    assert edhen.discount_pct > 45          # chronically discounted
    assert edhen.discounted_share == 1.0
    assert edhen.gender == "men"
    assert by_brand["Golden Goose"].sneaker_share == 1.0


def test_shopify_collector_filters_non_shoes(fetcher):
    cfg = source(type="shopify", enabled=True, pages=1, gender="men", scheme="http",
                 shops=[{"domain": "fixture", "collections": ["uomo-scarpe"]}])
    items = list(ShopifyCollector("demo_shopify", cfg, fetcher).iter_items())
    brands = {i.brand for i in items}
    assert "Barbour" not in brands          # outerwear, filtered out
    assert {"Edhèn Milano", "Fabi", "Autry"} <= brands
    edhen = [i for i in items if i.brand == "Edhèn Milano"]
    assert all(i.discount_pct and i.discount_pct > 45 for i in edhen)


def test_missing_page_is_handled(fetcher):
    cfg = source(**(HTML_SOURCE | {"start_urls": ["http://fixture/missing-{page}.html"]}))
    assert list(HtmlListingCollector("demo", cfg, fetcher).iter_items()) == []
