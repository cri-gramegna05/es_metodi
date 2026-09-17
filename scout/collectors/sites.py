"""Per-marketplace presets. Selectors live here so config.yaml stays short;
override any of them under sources.<name>.selectors when a site changes its markup.
"""

from __future__ import annotations

from .html_source import HtmlListingCollector


class FarfetchCollector(HtmlListingCollector):
    type = "farfetch"
    default_start_urls = [
        "https://www.farfetch.com/it/shopping/men/shoes-2/items.aspx?page={page}&view=180"
    ]
    default_selectors = {
        "item": "li[data-testid='productCard']",
        "brand": "[data-component='ProductCardBrandName']",
        "title": "[data-component='ProductCardDescription']",
        "price": "[data-component='PriceFinal'], [data-component='Price']",
        "full_price": "[data-component='PriceOriginal']",
        "link": "a",
    }


class YooxCollector(HtmlListingCollector):
    type = "yoox"
    default_start_urls = [
        "https://www.yoox.com/it/uomo/scarpe/shoponline?page={page}"
    ]
    default_selectors = {
        "item": "div.item",
        "brand": ".itemContainer .brand, .item-brand",
        "title": ".itemContainer .title, .item-title",
        "price": ".itemContainer .newprice, .price .new",
        "full_price": ".itemContainer .oldprice, .price .old",
        "link": "a",
    }


class GiglioCollector(HtmlListingCollector):
    type = "giglio"
    default_start_urls = [
        "https://www.giglio.com/it/uomo/scarpe?p={page}"
    ]
    default_selectors = {
        "item": "li.product-item, div.product-item",
        "brand": ".product-brand, .brand",
        "title": ".product-name, .product-item-link",
        "price": ".special-price .price, .price",
        "full_price": ".old-price .price",
        "link": "a.product-item-link, a",
    }
