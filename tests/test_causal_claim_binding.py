"""Causal wording is not verified by a declared design and a significant result."""

import itertools

import pytest
import statwarrant as sw


METADATA = {
    "outcome": "exam score",
    "contrast": "treatment minus control",
    "scope": "students",
}


@pytest.fixture
def randomised_result():
    return sw.declare(design="randomised", **METADATA).analyze(estimate=4, se=1)


def parts(result, sentence, rule):
    return [p for p in result.check(sentence, record=False).parts if p.rule == rule]


@pytest.mark.parametrize("sentence", [
    "The treatment caused cancer.",
    "Smoking caused a change in exam score.",
    "The treatment caused a change in exam score.",
])
def test_reported_causal_examples_require_review(randomised_result, sentence):
    out = randomised_result.check(sentence, record=False)
    causal = [p for p in out.parts if p.rule == "causal"]
    assert out.level == "check"
    assert len(causal) == 1 and causal[0].status == "check"
    assert causal[0].text == "caused"
    assert [sentence[start:end] for start, end in causal[0].spans] == ["caused"]
    for missing_check in ("intervention", "outcome", "contrast", "scope", "assumptions"):
        assert missing_check in causal[0].reason
    assert causal[0].action


@pytest.mark.parametrize("present", list(itertools.product([False, True], repeat=3)))
def test_all_metadata_combinations_require_review(present):
    metadata = {key: value for (key, value), include in zip(METADATA.items(), present) if include}
    result = sw.declare(design="randomised", **metadata).analyze(estimate=4, se=1)
    causal = parts(result, "The treatment caused a change in exam score.", "causal")
    assert len(causal) == 1 and causal[0].status == "check"


@pytest.mark.parametrize("design", [None, "randomised", "randomized", "RCT"])
@pytest.mark.parametrize("estimate", [4, 1, -4])
def test_design_alias_and_significance_do_not_approve_causality(design, estimate):
    result = sw.declare(design=design).analyze(estimate=estimate, se=1)
    causal = parts(result, "The treatment caused cancer.", "causal")
    assert len(causal) == 1 and causal[0].status == "check"


@pytest.mark.parametrize("sentence", [
    "The treatment led to a change in exam score.",
    "The treatment resulted in a change in exam score.",
    "Exam scores were due to the treatment.",
])
def test_other_recognised_causal_phrases_require_review(randomised_result, sentence):
    causal = parts(randomised_result, sentence, "causal")
    assert len(causal) == 1 and causal[0].status == "check"


def test_observational_positive_causal_conflict_is_preserved():
    result = sw.declare(design="observational", **METADATA).analyze(estimate=4, se=1)
    causal = parts(result, "Smoking caused a change in exam score.", "causal")
    assert len(causal) == 1 and causal[0].status == "conflict"


def test_negated_causal_claim_is_not_approved(randomised_result):
    out = randomised_result.check("The treatment did not cause cancer.", record=False)
    assert parts(randomised_result, out.sentence, "causal")[0].status == "check"
    assert parts(randomised_result, out.sentence, "unattached-negation")[0].status == "check"
    assert out.level == "check"


def test_independent_negated_effect_conflict_is_preserved(randomised_result):
    sentence = "The treatment caused no change in exam score."
    assert parts(randomised_result, sentence, "causal")[0].status == "check"
    assert parts(randomised_result, sentence, "no-effect")[0].status == "conflict"


@pytest.mark.parametrize("design", ["randomised", "observational", None])
def test_cautions_remain_distinct_from_affirmative_claims(design):
    result = sw.declare(design=design, **METADATA).analyze(estimate=4, se=1)
    sentence = "The data cannot prove cause and effect."
    out = result.check(sentence, record=False)
    assert parts(result, sentence, "caution")[0].status == "consistent"
    assert out.level != "conflict"
    assert all(p.status != "consistent" for p in parts(result, sentence, "causal"))
    assert not parts(result, sentence, "unattached-negation")


@pytest.mark.parametrize("sentence", [
    "The treatment caused cancer because the data do not prove it.",
    "Whether smoking caused cancer because treatment caused a change in exam score is unknown.",
    "The study does not prove the treatment caused cancer and smoking caused cancer.",
])
def test_caution_scope_cannot_approve_a_causal_hit(randomised_result, sentence):
    causal = parts(randomised_result, sentence, "causal")
    assert causal and all(p.status == "check" for p in causal)


def test_proof_and_universality_remain_independent_conflicts(randomised_result):
    sentence = "The treatment proved it caused cancer for everyone."
    assert parts(randomised_result, sentence, "certainty")[0].status == "conflict"
    assert parts(randomised_result, sentence, "causal")[0].status == "check"
    assert parts(randomised_result, sentence, "generalization")[0].status == "conflict"


def test_nearby_caution_does_not_clear_independent_proof(randomised_result):
    sentence = "The study proves it caused cancer; it cannot prove a result."
    assert parts(randomised_result, sentence, "certainty")[0].status == "conflict"
    assert parts(randomised_result, sentence, "caution")[0].status == "consistent"
    assert parts(randomised_result, sentence, "causal")[0].status == "check"


@pytest.mark.parametrize("value,status", [(4, "consistent"), (99, "conflict")])
def test_independent_estimate_is_still_checked(randomised_result, value, status):
    sentence = f"The treatment caused cancer and the estimate was {value}."
    assert parts(randomised_result, sentence, "causal")[0].status == "check"
    assert parts(randomised_result, sentence, "reported-number")[0].status == status


def test_independent_p_value_conflict_is_preserved(randomised_result):
    sentence = "The treatment caused cancer and the estimate was 4 and p = 0.5."
    assert parts(randomised_result, sentence, "causal")[0].status == "check"
    assert parts(randomised_result, sentence, "reported-number")[0].status == "consistent"
    assert parts(randomised_result, sentence, "p-value")[0].status == "conflict"


def test_unrecognized_causal_synonym_remains_a_documented_detection_gap(randomised_result):
    out = randomised_result.check("The treatment induced cancer.", record=False)
    assert not any(p.rule == "causal" for p in out.parts)
    assert out.status == "no_supported_pattern"
    assert any("induced cancer" in fragment for fragment in out.unchecked)


def test_unrecognized_causal_synonym_can_coexist_with_no_warnings(randomised_result):
    sentence = "The treatment induced cancer and the effect was significant."
    out = randomised_result.check(sentence, record=False)
    assert out.status == "no_warnings"
    assert [(p.rule, p.status) for p in out.parts] == [("significance", "consistent")]
    assert any("induced cancer" in fragment for fragment in out.unchecked)


def test_existing_cause_of_death_gap_can_omit_unchecked_text(randomised_result):
    sentence = "The treatment is the cause of death and the effect was statistically significant."
    out = randomised_result.check(sentence, record=False)
    # This is a characterized pre-existing defect, not an endorsement of the
    # output: the currently suppressed phrase is absent from both collections.
    assert out.status == "no_warnings"
    assert [(p.rule, p.status) for p in out.parts] == [("significance", "consistent")]
    assert not any("cause of death" in p.text for p in out.parts)
    assert not any("cause of death" in fragment for fragment in out.unchecked)


def test_observational_negation_and_caution_are_known_heuristic_limitations():
    result = sw.declare(design="observational", **METADATA).analyze(estimate=4, se=1)
    negated = result.check("The treatment did not cause cancer.", record=False)
    assert [(p.rule, p.status) for p in negated.parts] == [
        ("unattached-negation", "check"), ("causal", "conflict")
    ]  # false conflict: the causal assertion is negated
    caution = result.check("Treatment caused cancer because the study cannot prove a result.", record=False)
    assert [(p.rule, p.status) for p in caution.parts] == [
        ("causal", "check"), ("caution", "consistent")
    ]  # the caution affects the causal hit despite unclear scope
