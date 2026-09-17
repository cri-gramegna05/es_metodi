"""Who deserves a notification. Pure logic, so it can be tested without any I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..config import NotifyConfig

Kind = Literal["new", "score_up", "score_down"]


@dataclass
class Notification:
    slug: str
    brand: str
    kind: Kind
    score: int
    old_score: int | None
    reason: str


def decide(candidates: list[dict[str, Any]], cfg: NotifyConfig) -> list[Notification]:
    """A brand is worth pinging about only if it is new, or moved a lot."""
    out: list[Notification] = []
    for c in candidates:
        score, old = c["score"], c.get("old_score")
        if score < cfg.min_score:
            continue
        if c.get("is_new") or old is None:
            out.append(Notification(c["slug"], c["brand"], "new", score, old,
                                    f"nuovo candidato, score {score}"))
            continue
        delta = score - old
        if abs(delta) > cfg.score_delta_threshold:
            kind: Kind = "score_up" if delta > 0 else "score_down"
            out.append(Notification(c["slug"], c["brand"], kind, score, old,
                                    f"score {old} -> {score} ({delta:+d})"))
    return out


def format_message(notification: Notification, candidate: dict[str, Any]) -> str:
    """Telegram message body (Markdown)."""
    price = (
        f"{candidate['price_min']:.0f}-{candidate['price_max']:.0f} EUR"
        if candidate.get("price_min") else "n/d"
    )
    cls = candidate.get("classification") or {}
    head = "*Nuovo candidato*" if notification.kind == "new" else "*Score aggiornato*"
    lines = [
        f"{head}: *{notification.brand}*",
        f"score: *{notification.score}*"
        + (f" (prima {notification.old_score})" if notification.old_score is not None else ""),
        f"prezzo: {price} | sconto medio: "
        + (f"{candidate['discount_pct']:.0f}%" if candidate.get("discount_pct") is not None
           else "n/d")
        + f" | item: {candidate.get('n_items', 0)}",
        f"fonti: {', '.join(candidate.get('sources', []))}",
    ]
    if cls:
        lines.append(
            f"posizionamento: {cls.get('positioning', '?')} | "
            f"fondatore: {cls.get('founder_type', '?')}"
        )
        if cls.get("red_flags"):
            lines.append(f"red flags: {', '.join(cls['red_flags'])}")
        if cls.get("rationale"):
            lines.append(f"_{cls['rationale']}_")
    if candidate.get("revenue_estimate_eur"):
        lines.append(f"stima fatturato: ~{candidate['revenue_estimate_eur']:,.0f} EUR")
    return "\n".join(lines)
