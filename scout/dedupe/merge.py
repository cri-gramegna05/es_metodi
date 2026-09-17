"""Cross-source brand merging: slug match first, fuzzy match as fallback."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from .normalize import brand_slug, normalize_name


@dataclass
class Resolution:
    slug: str
    display_name: str
    matched_existing: bool
    score: float = 100.0


class BrandResolver:
    """Maps raw source names to a stable slug, remembering what it has seen."""

    def __init__(self, known: dict[str, str] | None = None, threshold: int = 92) -> None:
        # slug -> display name
        self.known: dict[str, str] = dict(known or {})
        self.threshold = threshold

    def resolve(self, raw_name: str) -> Resolution:
        slug = brand_slug(raw_name)
        display = normalize_name(raw_name)
        if not slug:
            raise ValueError(f"cannot slug brand name: {raw_name!r}")
        if slug in self.known:
            return Resolution(slug, self.known[slug], matched_existing=True)

        match = process.extractOne(
            slug, list(self.known.keys()), scorer=fuzz.token_sort_ratio,
            score_cutoff=self.threshold,
        )
        if match:
            best_slug, score, _ = match
            # Guard against short slugs where fuzzy matching is unreliable.
            if min(len(slug), len(best_slug)) >= 6:
                return Resolution(best_slug, self.known[best_slug], True, float(score))

        self.known[slug] = display
        return Resolution(slug, display, matched_existing=False)
