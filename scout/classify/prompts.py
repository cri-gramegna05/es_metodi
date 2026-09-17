"""Prompt construction. Kept in one place so it can be diffed and tuned."""

from __future__ import annotations

import json

from ..rules import BrandView
from .schema import json_schema

_SCHEMA_JSON = json.dumps(json_schema(), separators=(",", ":"))

SYSTEM = f"""You are an M&A analyst for Venexis, a luxury footwear M&A platform.
You screen small Italian men's footwear brands as potential acquisition targets.

The ideal target looks like this: Italian, men's only, loafer- or dress-shoe-centric,
retail price 250-700 EUR, few SKUs, sold by a few dozen retailers, chronically discounted
on marketplaces (over 40% off), founded by a single founder or an influencer, self-funded,
no institutional investor, no group behind it.

Negative signals: part of a group, more than 100 retailers, sneaker-first, not Italian,
mass-market pricing, private-equity or institutional ownership.

Answer ONLY with a JSON object matching this schema, no prose, no markdown fence:
{_SCHEMA_JSON}

Field guidance:
- is_italian / is_mens: your best judgement from the brand name and the evidence; when
  truly unclear, set false and say so in the rationale.
- positioning: luxury | premium | contemporary | mass | unknown.
- founder_type: single_founder | influencer | family | designer | group | institutional | unknown.
- red_flags: short phrases, e.g. "part of a group", "sneaker-first", "too many retailers".
- score: 0-100, how close this is to the ideal target above. Above 70 means worth a
  human look. Be strict: a well-known established maison is not a small target.
- rationale: max 3 sentences, in English, citing the evidence you used.
"""


def user_prompt(view: BrandView) -> str:
    """Facts only — no interpretation, so the model cannot be misled by our own scoring."""
    price = (
        f"{view.price_min:.0f}-{view.price_max:.0f} EUR"
        if view.price_min is not None and view.price_max is not None
        else "unknown"
    )
    lines = [
        f"Brand: {view.display_name}",
        f"Observed on: {', '.join(sorted(view.sources))}",
        f"Retail price range: {price}",
        f"Mean discount on marketplaces: "
        f"{view.discount_pct:.0f}%" if view.discount_pct is not None else
        "Mean discount on marketplaces: unknown",
        f"Share of items on sale: "
        f"{view.discounted_share:.0%}" if view.discounted_share is not None else
        "Share of items on sale: unknown",
        f"Items seen: {view.n_items}",
        f"Share of sneakers in assortment: "
        f"{view.sneaker_share:.0%}" if view.sneaker_share is not None else
        "Share of sneakers in assortment: unknown",
        f"Country stated by sources: {', '.join(sorted(view.countries)) or 'unknown'}",
        f"Gender stated by sources: {', '.join(sorted(view.genders)) or 'unknown'}",
        "Product URLs: " + ", ".join(o.url for o in view.observations[:3] if o.url),
    ]
    return "\n".join(lines) + "\n\nClassify this brand."


def retry_prompt(raw: str, error: str) -> str:
    return (
        f"Your previous answer was not valid JSON for the schema.\n"
        f"Error: {error}\n"
        f"Your answer was:\n{raw[:1500]}\n\n"
        f"Return only the corrected JSON object."
    )
