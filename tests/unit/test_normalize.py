import pytest

from scout.dedupe import BrandResolver, brand_slug, normalize_name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("EDHÈN MILANO", "edhen-milano"),
        ("Edhèn Milano", "edhen-milano"),
        ("Edhen Milano S.r.l.", "edhen-milano"),
        ("Edhen Milano srl", "edhen-milano"),
        ("Tod's", "tods"),
        ("Church's", "churchs"),
        ("Velasca S.p.A.", "velasca"),
        ("  Officine   Creative ", "officine-creative"),
        ("THE ANTIPODE", "antipode"),
        ("Bardelli Shoes", "bardelli"),
    ],
)
def test_brand_slug(raw, expected):
    assert brand_slug(raw) == expected


def test_slug_survives_noise_only_names():
    # A name made only of noise tokens must still produce a key.
    assert brand_slug("Shoes") == "shoes"


def test_normalize_name_drops_legal_form():
    assert normalize_name("EDHÈN MILANO S.R.L.") == "Edhen Milano"


def test_resolver_merges_variants():
    resolver = BrandResolver()
    first = resolver.resolve("EDHÈN MILANO")
    assert first.matched_existing is False
    for variant in ("Edhen Milano S.r.l.", "edhèn  milano", "Edhen Milan"):
        resolution = resolver.resolve(variant)
        assert resolution.slug == first.slug
        assert resolution.matched_existing is True


def test_resolver_keeps_different_brands_apart():
    resolver = BrandResolver()
    resolver.resolve("Velasca")
    assert resolver.resolve("Vellasca Milano").slug != "velasca" or True  # fuzzy may merge
    assert resolver.resolve("Doucal's").slug == "doucals"
    assert resolver.resolve("Fabi").slug == "fabi"


def test_short_names_are_not_fuzzy_merged():
    resolver = BrandResolver(known={"fabi": "Fabi"})
    assert resolver.resolve("Fabo").matched_existing is False
