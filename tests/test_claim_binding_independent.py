"""Independent regressions for issues reported after the 0.5.0 PyPI release.

These examples test safety behavior on known counterexamples; they do not measure
accuracy on unseen scientific text.
"""

import pytest
import statwarrant as sw


def _parts(checked, rule):
    return [part for part in checked.parts if part.rule == rule]


@pytest.mark.parametrize(
    "declared,sentence",
    [
        ("men with diabetes", "The effect was significant in women with diabetes."),
        ("women with diabetes", "The effect was significant in men with diabetes."),
        ("men with diabetes", "The effect was significant in men without diabetes."),
        ("men with diabetes", "The effect was significant in men with diabetes and women with diabetes."),
    ],
)
def test_reported_or_ambiguous_subgroups_are_not_approved(declared, sentence):
    result = sw.declare(subgroup=declared, scope=declared).analyze(estimate=4, se=1)
    checked = result.check(sentence, record=False)
    subgroup = _parts(checked, "subgroup")
    assert subgroup, "Expected the subgroup rule to recognize the claim"
    assert any(p.status in {"check", "conflict"} for p in subgroup)
    assert not any(p.status == "consistent" for p in subgroup)
    assert checked.to_dict()["status"] != "no_warnings"


def test_exact_subgroup_does_not_become_an_incorrect_conflict():
    result = sw.declare(subgroup="men with diabetes", scope="men with diabetes").analyze(estimate=4, se=1)
    checked = result.check("The effect was significant in men with diabetes.", record=False)
    subgroup = _parts(checked, "subgroup")
    assert subgroup
    assert not any(p.status == "conflict" for p in subgroup)


@pytest.mark.parametrize("sentence", [
    "The treatment caused cancer.",
    "Smoking caused a change in exam score.",
    "The treatment caused a change in exam score.",
])
def test_randomised_design_alone_does_not_approve_causal_claim(sentence):
    result = sw.declare(design="randomised", outcome="exam score", contrast="treatment minus control", scope="students").analyze(estimate=4, se=1)
    checked = result.check(sentence, record=False)
    causal = _parts(checked, "causal")
    assert causal
    assert any(p.status in {"check", "conflict"} for p in causal)
    assert not any(p.status == "consistent" for p in causal)
    assert checked.to_dict()["status"] != "no_warnings"


@pytest.mark.parametrize("metadata", [
    {"design": "randomised", "outcome": "exam score"},
    {"design": "randomised", "contrast": "treatment minus control"},
    {"design": "randomised"},
])
def test_randomised_causal_claim_with_incomplete_metadata_requests_review(metadata):
    result = sw.declare(**metadata).analyze(estimate=4, se=1)
    causal = _parts(result.check("The treatment caused a change in exam score.", record=False), "causal")
    assert causal and all(p.status != "consistent" for p in causal)
    assert any(p.status in {"check", "conflict"} for p in causal)


def test_causal_check_does_not_hide_a_separate_significance_claim():
    result = sw.declare(design="randomised", outcome="exam score", contrast="treatment minus control").analyze(estimate=4, se=1)
    checked = result.check("The treatment caused cancer and the effect was statistically significant.", record=False)
    assert any(p.status == "check" for p in _parts(checked, "causal"))
    assert any(p.status == "consistent" for p in _parts(checked, "significance"))
