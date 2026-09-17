import json

import pytest

from scout.classify import Classification, Classifier, StubBackend
from scout.classify.classifier import ClassificationFailed, extract_json
from scout.classify.prompts import user_prompt
from scout.config import ClassifyConfig
from scout.models import Observation
from scout.rules import BrandView

VALID = {
    "is_italian": True, "is_mens": True, "positioning": "premium",
    "founder_type": "influencer", "red_flags": ["chronic discounting"],
    "score": 88, "rationale": "Small Italian loafer brand, heavily discounted.",
}


def view() -> BrandView:
    obs = Observation(
        brand="Edhèn Milano", source="demo", url="https://example.com/p/1",
        price_min=265.0, price_max=330.0, discount_pct=50.0, discounted_share=1.0,
        sneaker_share=0.0, n_items=6, gender="men",
    )
    return BrandView.build("edhen-milano", "Edhen Milano", [obs])


class ScriptedBackend:
    """Returns canned responses in order; records the messages it received."""

    name = "scripted"

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def generate(self, system, messages, schema):
        self.calls.append(list(messages))
        return self.responses.pop(0) if self.responses else "{}"


@pytest.mark.parametrize("raw", [
    json.dumps(VALID),
    f"```json\n{json.dumps(VALID)}\n```",
    f"Here you go:\n{json.dumps(VALID)}\nHope that helps.",
])
def test_extract_json_tolerates_wrapping(raw):
    assert extract_json(raw)["score"] == 88


def test_valid_answer_is_parsed():
    backend = ScriptedBackend(json.dumps(VALID))
    result = Classifier(ClassifyConfig(), backend).classify(view())
    assert result.score == 88 and result.founder_type == "influencer"


def test_invalid_json_is_retried_with_the_error():
    backend = ScriptedBackend("{ is_italian: yes }", json.dumps(VALID))
    result = Classifier(ClassifyConfig(max_retries=3), backend).classify(view())
    assert result.score == 88
    # Second attempt carries the previous answer and the validation error.
    assert len(backend.calls) == 2
    retry_text = backend.calls[1][-1]["content"]
    assert "not valid JSON" in retry_text and "is_italian" in retry_text


def test_out_of_range_score_is_retried():
    backend = ScriptedBackend(json.dumps(VALID | {"score": 140}), json.dumps(VALID))
    assert Classifier(ClassifyConfig(), backend).classify(view()).score == 88


def test_gives_up_after_max_retries():
    backend = ScriptedBackend("nope", "still nope")
    with pytest.raises(ClassificationFailed):
        Classifier(ClassifyConfig(max_retries=2), backend).classify(view())
    assert len(backend.calls) == 2


def test_junk_enum_and_flags_are_coerced():
    raw = VALID | {"positioning": "", "founder_type": None, "red_flags": "one flag"}
    parsed = Classification.model_validate(raw)
    assert parsed.positioning == "unknown" and parsed.founder_type == "unknown"
    assert parsed.red_flags == ["one flag"]


def test_prompt_states_facts_without_our_score():
    text = user_prompt(view())
    assert "Edhen Milano" in text and "265-330 EUR" in text and "50%" in text
    assert "prescore" not in text.lower()


def test_stub_backend_returns_valid_json():
    backend = StubBackend()
    raw = backend.generate("", [{"role": "user", "content": user_prompt(view())}], {})
    parsed = Classification.model_validate(json.loads(raw))
    assert parsed.score > 0 and parsed.is_mens
