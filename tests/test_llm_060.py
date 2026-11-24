"""The language-model layer: the model reads, statwarrant decides. No network: fake models."""

import json
from types import SimpleNamespace

import pytest

import statwarrant as sw
from statwarrant.llm import AnthropicLLM, CallableLLM, OpenAILLM, REWRITE_SYSTEM


def _res(est=4.2):
    plan = sw.declare(sesoi=3, sesoi_source="smallest gain teachers act on", units="points",
                      scope="first-year students, one university", outcome="exam score",
                      contrast="new method minus existing method")
    return plan.analyze(estimate=est, se=1.6, df=58)


def fake(extract, rewrite=None, calls=None):
    """A model that answers extraction with ``extract`` (a dict, or a function of the sentence)."""
    def fn(system, user):
        if calls is not None:
            calls.append((system, user))
        sentence = user.rsplit("Sentence:\n", 1)[-1]
        if system == REWRITE_SYSTEM:
            return json.dumps({"rewrite": rewrite})
        out = extract(sentence) if callable(extract) else extract
        return "```json\n" + json.dumps(out) + "\n```"
    return CallableLLM(fn)


NO_EFFECT = {"assertions": [{"kind": "no_effect", "direction": None, "value": None, "polarity": "asserted",
                             "quote": "had no effect"}], "meaning": []}


def test_conflict_found_and_checked_rewrite_offered():
    res = _res()
    allowed = res.claims.allowed[0].text

    def extract(sentence):
        return NO_EFFECT if "no effect" in sentence else {"assertions": [
            {"kind": "nonzero", "direction": "positive", "polarity": "asserted", "quote": "positive"}], "meaning": []}

    out = res.review("The new method had no effect on exam scores.", fake(extract, rewrite=allowed))
    assert out.level == "conflict"
    assert out.verdicts[0].status == "contradicted"
    assert out.suggestion == allowed
    assert out.suggestion_rules.level != "conflict"
    assert res.to_dict()["reviewed_sentences"][0]["suggestion"] == allowed
    assert "Sentences reviewed with a language model" in res.to_markdown()


def test_rewrite_that_still_conflicts_is_discarded():
    res = _res()
    out = res.review("The new method had no effect.", fake(NO_EFFECT, rewrite="There was no effect at all."))
    assert out.suggestion is None
    assert any("discarded" in e for e in out.errors)


def test_model_is_not_shown_the_numbers():
    calls = []
    res = _res()
    res.review("Scores improved.", fake({"assertions": [], "meaning": []}, calls=calls), rewrite=False)
    system, user = calls[0]
    for number in ("4.2", "1.6", "0.997", "7.4", "0.011"):
        assert number not in user
    assert "new method minus existing method" in user and "Scores improved." in user


def test_meaning_notes_are_to_verify():
    res = _res()
    extract = {"assertions": [{"kind": "nonzero", "direction": "positive", "quote": "better"}],
               "meaning": [{"quote": "at reasoning", "concern": "The outcome is exam score, not reasoning."}]}
    out = res.review("The new method made students better at reasoning.", fake(extract), rewrite=False)
    assert out.level == "to_verify"
    assert out.meaning[0]["concern"].startswith("The outcome")


def test_failures_fall_back_to_the_rules():
    res = _res()

    def broken(system, user):
        raise RuntimeError("no network")

    out = res.review("There is no effect.", CallableLLM(broken))
    assert out.verdicts == [] and out.rules.level == "conflict"
    assert out.level == "conflict" and "could not be used" in out.errors[0]
    out = res.review("There is no effect.", CallableLLM(lambda s, u: "I think it is fine."))
    assert "could not be used" in out.errors[0]
    bad = {"assertions": [{"kind": "proves", "quote": "proves"}], "meaning": []}
    out = res.review("This proves it.", fake(bad), rewrite=False)
    assert any("not usable" in e for e in out.errors) and out.level != "no_warnings"


def test_record_false_keeps_the_report_clean():
    res = _res()
    res.review("There is no effect.", fake(NO_EFFECT), rewrite=False, record=False)
    assert res.reviews == [] and res.checked == []


def test_provider_adapters_call_their_clients():
    seen = {}

    def anthropic_create(**kw):
        seen["anthropic"] = kw
        return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"assertions": [], "meaning": []}')])

    client = SimpleNamespace(messages=SimpleNamespace(create=anthropic_create))
    llm = AnthropicLLM(model="test-model", client=client)
    assert json.loads(llm.complete("sys", "user")) == {"assertions": [], "meaning": []}
    assert seen["anthropic"]["system"] == "sys" and seen["anthropic"]["model"] == "test-model"

    def openai_create(**kw):
        seen["openai"] = kw
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=openai_create)))
    llm = OpenAILLM(model="local", client=client)
    assert llm.complete("sys", "user") == "{}"
    assert seen["openai"]["messages"][0] == {"role": "system", "content": "sys"}
    with pytest.raises(ValueError):
        AnthropicLLM(model="", client=client)
