"""Direction binding regressions; the grammar is intentionally not a language parser."""

import json

import pytest

import statwarrant as sw


@pytest.fixture
def iris():
    return sw.declare(contrast="versicolor minus virginica", outcome="petal length", units="cm").analyze(
        estimate=-1.292, se=0.1
    )


def check(result, text):
    return result.check(text, record=False)


def direction(out):
    return [part for part in out.parts if part.rule == "direction"]


def assert_direction_review(out):
    assert out.status == "warnings", str(out)
    assert direction(out), str(out)
    assert all(part.status == "check" for part in direction(out)), str(out)
    assert all(part.action and "contrast" in part.reason for part in direction(out))


@pytest.mark.parametrize("text,status", [
    ("Petal length was lower for virginica than for versicolor.", "conflict"),
    ("Petal length was higher for virginica than for versicolor.", "consistent"),
    ("Petal length was lower for versicolor than for virginica.", "consistent"),
    ("Petal length was higher for versicolor than for virginica.", "conflict"),
])
def test_exact_named_group_comparison_uses_declared_order(iris, text, status):
    out = check(iris, text)
    assert [p.status for p in direction(out)] == [status], str(out)
    assert out.status == ("no_warnings" if status == "consistent" else "warnings")
    assert out.level == (None if status == "consistent" else "conflict")
    assert out.sentence[direction(out)[0].spans[0][0]:direction(out)[0].spans[0][1]] == direction(out)[0].text


def test_reversed_declared_contrast_reverses_binding():
    result = sw.declare(contrast="virginica minus versicolor", outcome="petal length").analyze(
        estimate=-1.292, se=0.1
    )
    assert check(result, "Petal length was lower for virginica than for versicolor.").status == "no_warnings"
    assert check(result, "Petal length was higher for virginica than for versicolor.").level == "conflict"


@pytest.mark.parametrize("text", [
    "Petal length was higher for virginica than for versicolor, and virginica was lower than versicolor.",
    "Versicolor was lower than virginica, whereas virginica was higher than versicolor.",
    "The effect was negative, but petal length was lower for virginica than for versicolor.",
    "In 2024, petal length was higher for virginica than for versicolor.",
    "Petal length was higher for virginica than for versicolor after adjustment.",
    "Petal length was higher for virginica than for versicolor extra.",
    "Petal length was higher for virginica than for virginica.",
    "Petal length was higher for virginica.",
    "Petal length was lower.",
    "Virginica scored lower than versicolor.",
    "Versicolor scored lower than virginica.",
    "Virginica outperformed versicolor.",
    "Virginica beat versicolor.",
])
def test_unbound_repeated_partial_or_mixed_clauses_need_review(iris, text):
    assert_direction_review(check(iris, text))


@pytest.mark.parametrize("text", [
    "Petal length was not lower for virginica than for versicolor.",
    "Petal length did not increase from virginica to versicolor.",
    "Petal length was no more than versicolor.",
])
def test_comparative_negation_is_not_assigned_a_sign(iris, text):
    out = check(iris, text)
    affected = [p for p in out.parts if p.rule in ("direction", "no-effect", "significance")]
    assert affected and all(p.status == "check" for p in affected), str(out)
    assert not any(p.status == "conflict" for p in out.parts), str(out)


@pytest.mark.parametrize("text", [
    "Virginica had significantly lower petal length than versicolor.",
    "Virginica had significantly higher petal length than versicolor.",
    "The difference was statistically significant and lower for virginica than for versicolor.",
    "The difference was not significant, and petal length was lower for virginica than for versicolor.",
])
def test_folded_significance_never_reassures_or_conflicts_when_unbound(iris, text):
    out = check(iris, text)
    relevant = [p for p in out.parts if p.rule in ("direction", "significance", "nonsignificance")]
    assert relevant and all(p.status == "check" for p in relevant), str(out)
    assert not any(p.status == "conflict" for p in out.parts), str(out)


@pytest.mark.parametrize("text", [
    "Virginica had a 1.292 cm lower petal length than versicolor.",
    "Virginica had a 1.292 cm higher petal length than versicolor.",
    "Petal length was lower for virginica than for versicolor by 1.292 cm.",
    "Petal length was higher for virginica than for versicolor by 1.292 cm.",
])
def test_numeric_direction_is_not_compared_using_unbound_sign(iris, text):
    out = check(iris, text)
    assert_direction_review(out)
    affected = [p for p in out.parts if p.rule in ("magnitude", "reported-number")]
    assert affected and all(p.status == "check" for p in affected), str(out)
    assert not any(p.status == "conflict" for p in out.parts), str(out)


@pytest.mark.parametrize("text,expected", [
    ("Scores increased from day 2 to day 0.", "consistent"),
    ("Scores decreased from day 0 to day 2.", "consistent"),
    ("Scores decreased from day 2 to day 0.", "conflict"),
    ("Scores increased from day 0 to day 2.", "conflict"),
])
def test_exact_temporal_comparison_orients_toward_destination(text, expected):
    result = sw.declare(contrast="day 2 minus day 0", outcome="scores").analyze(estimate=-0.6, se=0.1)
    out = check(result, text)
    assert [p.status for p in direction(out)] == [expected], str(out)
    assert not any(p.rule == "unverified-number" for p in out.parts), str(out)
    assert out.status == ("no_warnings" if expected == "consistent" else "warnings")


@pytest.mark.parametrize("text", [
    "Scores increased from day 20 to day 0.",
    "In 2024, scores increased from day 2 to day 0.",
    "Scores increased from day 2 to day 0 and decreased from day 0 to day 2.",
    "Scores increased from day 2 to day 0, but decreased in another sample.",
])
def test_partial_temporal_labels_dates_and_clauses_need_review(text):
    result = sw.declare(contrast="day 2 minus day 0", outcome="scores").analyze(estimate=-0.6, se=0.1)
    assert_direction_review(check(result, text))


@pytest.mark.parametrize("contrast,outcome,text", [
    (None, "petal length", "Petal length was higher for virginica than for versicolor."),
    ("versicolor minus virginica", None, "Petal length was higher for virginica than for versicolor."),
    ("versicolor minus virginica", "sepal length", "Petal length was higher for virginica than for versicolor."),
    ("versicolor versus virginica", "petal length", "Petal length was higher for virginica than for versicolor."),
    ("versicolor minus virginica", "petal length", "Petal length was higher for virginica than for versicolor extra."),
    ("group a minus group ab", "scores", "Scores were higher for group a than for group abc."),
    ("lower school minus upper school", "scores", "Scores were higher for lower school than for upper school."),
    (None, None, "A outperformed B."),
    (None, None, "A scored lower than B."),
    (None, None, "Scores were lower with the program."),
    (None, None, "Scores were higher."),
    (None, None, "Virginica had more petal length."),
    (None, None, "Scores increased for virginica."),
    (None, None, "Scores increased from baseline."),
    (None, None, "Scores decreased after treatment."),
])
def test_missing_or_unsupported_binding_never_falls_back_to_substrings(contrast, outcome, text):
    result = sw.declare(contrast=contrast, outcome=outcome).analyze(estimate=-0.6, se=0.1)
    assert_direction_review(check(result, text))


def test_evidence_for_an_unbound_comparison_is_not_declared_consistent(iris):
    out = check(iris, "There is evidence that virginica is lower than versicolor.")
    assert_direction_review(out)
    assert [p.status for p in out.parts if p.rule == "evidence"] == ["check"]


@pytest.mark.parametrize("text", [
    "Scores increased for versicolor but decreased for virginica.",
    "Scores increased but also decreased.",
    "Scores decreased in one setting, while scores increased in another.",
])
def test_separate_direction_clauses_are_not_assumed_to_describe_one_contrast(text):
    result = sw.declare().analyze(estimate=-0.6, se=0.1)
    out = check(result, text)
    assert_direction_review(out)
    assert not any(p.status == "conflict" for p in direction(out))


def test_exact_multiword_labels_not_confused_by_shared_prefix():
    result = sw.declare(contrast="group a minus group ab", outcome="scores").analyze(estimate=-0.6, se=0.1)
    assert check(result, "Scores were lower for group a than for group ab.").status == "no_warnings"
    assert check(result, "Scores were lower for group ab than for group a.").level == "conflict"


def test_better_lower_does_not_invert_literal_higher_and_lower(iris):
    result = sw.declare(contrast="versicolor minus virginica", outcome="petal length", better="lower").analyze(
        estimate=-1.292, se=0.1
    )
    assert check(result, "Petal length was higher for virginica than for versicolor.").status == "no_warnings"
    assert check(result, "Petal length was lower for virginica than for versicolor.").level == "conflict"
    assert_direction_review(check(result, "Virginica was better than versicolor."))


def test_direct_signed_result_remains_usable(iris):
    assert check(iris, "The effect was negative.").status == "no_warnings"
    assert check(iris, "The effect was positive.").level == "conflict"
    assert check(iris, "The effect was -1.292 cm.").status == "no_warnings"


@pytest.mark.parametrize("estimate,se,sesoi", [
    (0.6, 0.1, 0.2), (0.3, 0.1, 0.2), (0.08, 0.03, 0.2),
    (0.02, 0.05, 0.2), (0.15, 0.2, 0.2), (-0.5, 0.1, 0.2), (-1.292, 0.1, None),
])
def test_generated_scalar_claims_remain_consistent_with_a_declared_contrast(estimate, se, sesoi):
    options = {"contrast": "a minus b", "outcome": "score", "scope": "one cohort"}
    if sesoi is not None:
        options.update(sesoi=sesoi, sesoi_source="test")
    result = sw.declare(**options).analyze(estimate=estimate, se=se)
    for claim in result.claims.allowed:
        out = check(result, claim.text)
        assert out.status == "no_warnings", str(out)


def test_recording_serialization_and_span_contracts(iris):
    text = "Virginica had significantly lower petal length than versicolor."
    out = iris.check(text, record=False)
    assert not iris.checked
    assert out.to_dict()["status"] == "warnings"
    for part in out.parts:
        assert [text[a:b] for a, b in part.spans] == part.text.split(" … ")
    iris.check(text)
    data = json.loads(iris.to_json())
    recorded = data["checked_sentences"][0]
    assert recorded["status"] == "warnings" and recorded["level"] == "check"
    assert all(p["status"] == "check" for p in recorded["warnings"])
    assert text in iris.to_markdown() and "check, direction" in iris.to_markdown()
