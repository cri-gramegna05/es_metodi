"""Brand-name normalization: one slug per real-world brand."""

from __future__ import annotations

import re
import unicodedata

# Legal forms and marketplace noise stripped before slugging.
LEGAL_SUFFIXES = {
    "srl", "s r l", "srls", "spa", "s p a", "snc", "s n c", "sas", "s a s",
    "sl", "sa", "ltd", "limited", "llc", "inc", "gmbh", "bv", "co", "company",
}
NOISE_TOKENS = {
    "the", "official", "store", "shop", "online", "outlet", "collection",
    "collections", "brand", "man", "men", "mens", "uomo", "donna", "woman",
    "women", "shoes", "scarpe", "calzature", "footwear",
}
_PUNCT_RE = re.compile(r"[^a-z0-9]+")
_APOSTROPHE_RE = re.compile(r"[\u2019'`]")
_MULTISPACE_RE = re.compile(r"\s+")
# "S.r.l." / "S p A" -> one token, so legal forms can be stripped as a unit.
_DOTTED_INITIALS_RE = re.compile(r"\b([a-z])[\s.]+([a-z])[\s.]*([a-z])?\b\.?")


def _collapse_initials(text: str) -> str:
    return _DOTTED_INITIALS_RE.sub(lambda m: "".join(g for g in m.groups() if g), text)


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def normalize_name(name: str) -> str:
    """Human-readable canonical form: 'EDHÈN  MILANO srl' -> 'Edhen Milano'."""
    cleaned = _MULTISPACE_RE.sub(" ", strip_accents(name)).strip(" -–—,.")
    tokens = [t for t in cleaned.split(" ") if t]
    while tokens and _PUNCT_RE.sub("", tokens[-1].lower()) in LEGAL_SUFFIXES:
        tokens.pop()
    if not tokens:
        tokens = cleaned.split(" ")
    return " ".join(t.capitalize() if t.isupper() or t.islower() else t for t in tokens)


def brand_slug(name: str) -> str:
    """Matching key: lowercase, accent-free, no punctuation, no legal/noise tokens."""
    # "Tod's" -> "tods", not "tod s".
    lowered = _APOSTROPHE_RE.sub("", strip_accents(name).lower())
    base = _PUNCT_RE.sub(" ", _collapse_initials(lowered)).strip()
    tokens = [t for t in base.split(" ") if t]
    # Drop legal suffixes anywhere, noise only when it is not the whole name.
    tokens = [t for t in tokens if t not in LEGAL_SUFFIXES]
    kept = [t for t in tokens if t not in NOISE_TOKENS]
    tokens = kept or tokens
    return "-".join(tokens)
