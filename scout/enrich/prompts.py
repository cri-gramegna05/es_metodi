"""Prompt for the deep-dive brief produced by Claude."""

from __future__ import annotations

from ..classify.schema import Classification
from ..rules import BrandView

SYSTEM = """You are an M&A analyst at Venexis, a luxury footwear M&A platform.

You research one small Italian men's footwear brand and write an internal one-page brief
for the deal team. Use web search to find the brand's own site, its about page, founder
interviews and trade press (Pambianco, MFF, Fashion Network, WWD, local press). Prefer
primary sources; if something cannot be verified, write "not verified" rather than guessing.

Write the brief in Markdown, in Italian, with exactly these sections:

## Storia
## Fondatori e assetto
## Prodotto e posizionamento
## Distribuzione
## Stima fatturato
## Segnali di stress
## Perché interessante per Venexis
## Prossimo passo

Rules:
- Ground every claim in what you found; cite the source inline as a Markdown link.
- "Stima fatturato": give a range in EUR with the reasoning (retailers x sell-in, or
  filed accounts if you find them). Say explicitly how confident you are.
- "Segnali di stress": chronic discounting, dormant social accounts, shrinking retailer
  list, unpaid suppliers, dropped collections.
- "Prossimo passo": one concrete action for the deal team.
- Keep the whole brief under 700 words.
- End with a single final line, outside the sections, in exactly this form:
  REVENUE_ESTIMATE_EUR: <number or "unknown">
  Use the midpoint of your range, digits only, no thousands separators.
"""


def user_prompt(view: BrandView, classification: Classification | None) -> str:
    price = (
        f"{view.price_min:.0f}-{view.price_max:.0f} EUR"
        if view.price_min is not None and view.price_max is not None
        else "unknown"
    )
    lines = [
        f"Brand: {view.display_name}",
        f"Seen on: {', '.join(sorted(view.sources))}",
        f"Retail price range observed: {price}",
        f"Mean marketplace discount: "
        + (f"{view.discount_pct:.0f}%" if view.discount_pct is not None else "unknown"),
        f"Items observed: {view.n_items}",
        f"Sneaker share of assortment: "
        + (f"{view.sneaker_share:.0%}" if view.sneaker_share is not None else "unknown"),
        "Product pages we saw: " + ", ".join(o.url for o in view.observations[:5] if o.url),
    ]
    if classification:
        lines += [
            "",
            "Our screening model said:",
            f"- score {classification.score}, positioning {classification.positioning}, "
            f"founder type {classification.founder_type}",
            f"- red flags: {', '.join(classification.red_flags) or 'none'}",
            f"- rationale: {classification.rationale}",
            "Treat that as a hypothesis to verify, not as fact.",
        ]
    return "\n".join(lines) + "\n\nResearch this brand and write the brief."
