import pytest

from scout.models import Observation
from scout.rules import BrandView, RuleEngine


def obs(**kwargs) -> Observation:
    base = dict(
        brand="Edhen Milano", source="demo", url="https://example.com",
        price_min=280.0, price_max=450.0, discount_pct=55.0, discounted_share=0.9,
        sneaker_share=0.0, n_items=12, country="IT", gender="men",
    )
    return Observation(**(base | kwargs))


def view(*observations, slug="edhen-milano") -> BrandView:
    return BrandView.build(slug, "Edhen Milano", list(observations) or [obs()])


@pytest.fixture
def engine(rules_cfg, scoring_cfg) -> RuleEngine:
    return RuleEngine(rules_cfg, scoring_cfg)


def test_ideal_target_passes_with_full_score(engine):
    result = engine.evaluate(view())
    assert result.passed
    assert result.prescore == 100
    assert set(result.signals) == {
        "price_in_band", "chronic_discount", "few_items", "italian", "mens"
    }


def test_blacklisted_group_is_dropped(engine):
    result = engine.evaluate(view(obs(), slug="tods"))
    assert not result.passed and "blacklisted" in result.reasons


def test_foreign_brand_is_dropped(engine):
    result = engine.evaluate(view(obs(country="FR")))
    assert not result.passed
    assert any("country=FR" in r for r in result.reasons)


def test_unknown_country_survives_for_the_llm(engine):
    result = engine.evaluate(view(obs(country=None)))
    assert result.passed
    assert "italian" not in result.signals


def test_women_only_is_dropped(engine):
    assert not engine.evaluate(view(obs(gender="women"))).passed


def test_price_band(engine):
    assert not engine.evaluate(view(obs(price_min=60.0, price_max=120.0))).passed
    assert not engine.evaluate(view(obs(price_min=1400.0, price_max=2200.0))).passed
    assert engine.evaluate(view(obs(price_min=210.0, price_max=260.0))).passed


def test_assortment_size(engine):
    assert not engine.evaluate(view(obs(n_items=400))).passed
    assert not engine.evaluate(view(obs(n_items=1))).passed


def test_sneaker_first_is_dropped(engine):
    result = engine.evaluate(view(obs(sneaker_share=0.8)))
    assert not result.passed
    assert any("sneaker-first" in r for r in result.reasons)


def test_low_discount_passes_without_the_signal(engine):
    result = engine.evaluate(view(obs(discount_pct=10.0)))
    assert result.passed and "chronic_discount" not in result.signals


def test_merge_across_sources_is_item_weighted(engine):
    merged = view(
        obs(source="a", n_items=10, discount_pct=50.0, price_min=280.0, price_max=400.0),
        obs(source="b", n_items=2, discount_pct=20.0, price_min=250.0, price_max=600.0),
    )
    assert merged.n_items == 12
    assert merged.price_min == 250.0 and merged.price_max == 600.0
    assert merged.discount_pct == 45.0
    assert engine.evaluate(merged).passed
