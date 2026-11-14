"""Conservative significance review for recognised but unbound comparisons.

These are targeted regression cases, not an accuracy estimate for scientific text.
"""

import numpy as np
import pytest
import re
from scipy import stats

import statwarrant as sw
from statwarrant.claims import _fmt_p_for_alpha, fmt_p


BASE = dict(sesoi=3, sesoi_source="illustrative only", units="points", scope="students")
CONTRAST = dict(outcome="exam score", contrast="new method minus existing method")


def _result(route, significant=False):
    if route.startswith("scipy"):
        rng = np.random.default_rng(7)
        new = rng.normal(64, 6, 30)
        old = rng.normal(60, 6, 30)
        assert not significant
        return sw.declare(**BASE, **(CONTRAST if route.endswith("contrast") else {})).analyze(
            stats.ttest_ind(new, old)
        )
    return sw.declare(**BASE, **(CONTRAST if route.endswith("contrast") else {})).analyze(
        estimate=4.2 if significant else 1.54, se=1.35, df=58
    )


def _parts(out, rule):
    return [part for part in out.parts if part.rule == rule]


@pytest.mark.parametrize("route", ["estimate, contrast", "scipy", "scipy, contrast"])
@pytest.mark.parametrize("sentence", [
    "The new method significantly improved scores.",
    "The new method significantly lowered scores.",
    "Scores were significantly different between the groups.",
    "Students taught with the new method scored significantly higher than those taught with the existing method.",
])
def test_unbound_significance_shows_own_zero_test_but_remains_check(route, sentence):
    res = _result(route)
    out = res.check(sentence, record=False)
    parts = _parts(out, "significance")
    assert not res.evidence.differs_from_zero
    assert parts and all(p.status == "check" for p in parts), str(out)
    assert out.status == "warnings" and out.level == "check"
    reason = parts[0].reason
    assert "not be tied to this result" in reason
    assert "two-sided test relative to its reference null is not significant" in reason
    assert "p = " + fmt_p(res.evidence.p_zero) in reason
    assert "alpha = 0.05" in reason
    assert "If the sentence asserts" in reason
    assert "that assertion would conflict with this result" in reason
    assert "test, reference null, threshold, outcome, groups" in reason
    assert "test, reference null, threshold" in parts[0].action


def test_reproduces_published_quickstart_scipy_data_and_conditional_warning():
    res = _result("scipy")
    assert res.evidence.p_zero == pytest.approx(0.2581533376889669)
    out = res.check("The new method significantly improved scores.", record=False)
    part = _parts(out, "significance")[0]
    assert out.level == "check" and part.status == "check"
    assert "p = 0.258" in part.reason
    assert "this same test and result" in part.reason


def test_scipy_nonzero_reference_null_is_not_represented_as_zero_on_original_scale():
    scipy_result = stats.ttest_1samp([99, 100, 101, 102, 103], 100)
    res = sw.declare().analyze(scipy_result)
    assert res.null == pytest.approx(100)
    assert res.evidence.p_zero == pytest.approx(float(scipy_result.pvalue))
    part = _parts(res.check("The mean was significantly greater than zero.", record=False), "significance")[0]
    assert part.status == "check"
    assert "test relative to its reference null" in part.reason
    assert "original scale may be nonzero, reconstructed or unknown" in part.reason
    assert "reference null" in part.action


@pytest.mark.parametrize("sentence", [
    "We hypothesised that the new method would significantly improve scores.",
    "Previous studies found that the method significantly improved scores.",
    "The new method was expected to significantly improve scores, but it did not.",
    "Group C scored significantly higher than group D.",
    "Among women, the new method significantly improved scores compared with the existing method.",
    "The new method significantly improved student attendance compared with the existing method.",
    "The new method significantly improved scores in the prespecified one-sided test.",
    "Model A was not significant but model B was significantly higher than model A.",
    "The new method did not, despite repeated attempts, significantly improve scores.",
])
def test_unbound_claims_do_not_turn_into_automatic_significance_conflicts(sentence):
    res = _result("estimate, contrast")
    out = res.check(sentence, record=False)
    parts = _parts(out, "significance")
    assert parts and all(p.status == "check" for p in parts), str(out)
    assert not any(p.rule == "significance" and p.status == "conflict" for p in out.parts)
    assert "same test and result" in parts[0].reason


@pytest.mark.parametrize("sentence", [
    "The new method failed to significantly improve scores.",
    "Whether the new method significantly improved scores is unclear.",
    "The new method did not significantly improve scores.",
    "The new method improved scores, though not significantly.",
])
def test_simple_negated_or_questioned_comparisons_have_no_false_conflict(sentence):
    out = _result("estimate, contrast").check(sentence, record=False)
    assert out.status == "warnings", str(out)
    assert not out.conflicts, str(out)
    assert _parts(out, "significance") or _parts(out, "nonsignificance")


@pytest.mark.xfail(raises=AssertionError, reason="Known pre-existing hedge-scope limitation without a comparison")
@pytest.mark.parametrize("significant", [False, True])
@pytest.mark.parametrize("sentence", [
    "Whether the result was statistically significant is unclear.",
    "The result failed to be statistically significant.",
])
def test_simple_hedges_are_reviewed_for_either_test_outcome(significant, sentence):
    out = _result("estimate", significant=significant).check(sentence, record=False)
    parts = _parts(out, "significance")
    assert parts and all(p.status == "check" for p in parts), str(out)
    assert not any(p.status == "conflict" for p in parts)


def test_same_result_unambiguous_significance_still_conflicts_when_nonsignificant():
    out = _result("estimate").check("The result was statistically significant.", record=False)
    parts = _parts(out, "significance")
    assert parts and all(p.status == "conflict" for p in parts), str(out)


def test_significant_zero_test_unbound_comparison_remains_review():
    res = _result("estimate, contrast", significant=True)
    assert res.evidence.differs_from_zero
    for sentence in ("The new method significantly improved scores.",
                     "The new method significantly lowered scores."):
        parts = _parts(res.check(sentence, record=False), "significance")
        assert parts and all(p.status == "check" for p in parts)
        assert "two-sided test relative to its reference null is significant" in parts[0].reason


def test_unbound_significance_does_not_hide_independent_p_value_conflict():
    out = _result("estimate, contrast").check(
        "The new method significantly improved scores; p = 0.9.", record=False
    )
    assert [p.status for p in _parts(out, "significance")] == ["check"]
    assert [p.status for p in _parts(out, "p-value")] == ["conflict"]


def test_named_equivalence_test_is_not_assumed_to_be_the_zero_test():
    res = _result("estimate, contrast")
    out = res.check("For the equivalence test, the result was significant.", record=False)
    parts = _parts(out, "significance")
    assert parts and all(p.status != "conflict" for p in parts), str(out)


@pytest.mark.parametrize("sentence", [
    "Scores increased; this result's minimal-effect test was significant.",
    "Scores increased; this result was statistically significant.",
])
def test_direction_in_separate_clause_does_not_hide_an_independent_conflict(sentence):
    res = sw.declare(sesoi=1, sesoi_source="example").analyze(estimate=0, se=0.5)
    out = res.check(sentence, record=False)
    parts = _parts(out, "significance")
    assert parts and all(p.status == "conflict" for p in parts), str(out)
    if "minimal-effect" in sentence:
        assert "minimal-effect test" in parts[0].reason


def test_direct_result_sign_conflict_is_not_hidden_by_comparison_review():
    res = sw.declare().analyze(estimate=0.3, se=0.1)
    out = res.check("The effect was significantly negative.", record=False)
    parts = _parts(out, "significance")
    assert parts and parts[0].status == "conflict", str(out)
    assert "opposite direction" in parts[0].reason


@pytest.mark.xfail(raises=AssertionError, reason="Known pre-existing direct-sign binding gap with a declared contrast")
def test_direct_result_sign_conflict_is_preserved_when_contrast_is_declared():
    res = sw.declare(outcome="score", contrast="A minus B").analyze(estimate=0.3, se=0.1)
    out = res.check("The effect was significantly negative.", record=False)
    parts = _parts(out, "significance")
    assert parts and parts[0].status == "conflict", str(out)
    assert "opposite direction" in parts[0].reason


@pytest.mark.parametrize("sentence", [
    "The result was significantly negative.",
    "The effect was significantly negative overall.",
    "The effect decreased significantly.",
])
def test_existing_significant_direction_conflicts_are_not_folded_away(sentence):
    res = sw.declare().analyze(estimate=0.3, se=0.1)
    out = res.check(sentence, record=False)
    assert out.level == "conflict", str(out)


def test_hedged_significance_does_not_hide_independent_direction_conflict():
    res = sw.declare().analyze(estimate=0.3, se=0.1)
    out = res.check("Whether the result was statistically significant is unclear; the effect was negative.",
                    record=False)
    assert out.level == "conflict", str(out)


@pytest.mark.parametrize("alpha,estimate,expected", [
    (0.04999, 1.96005, True),
    (0.05001, 1.9598, False),
])
def test_displayed_p_remains_on_its_real_side_of_alpha(alpha, estimate, expected):
    res = sw.declare(alpha=alpha, outcome="score", contrast="A minus B").analyze(estimate=estimate, se=1)
    assert res.evidence.differs_from_zero is expected
    out = res.check("The new method significantly improved scores.", record=False)
    part = _parts(out, "significance")[0]
    assert part.status == "check"
    displayed = re.search(r"p = ([0-9.eE+-]+)", part.reason)
    assert displayed, part.reason
    assert (float(displayed.group(1)) < alpha) is expected
    assert "rounded" in part.reason and "test statistic" in part.reason


@pytest.mark.parametrize("direction", [0.0, 1.0])
def test_p_format_preserves_adjacent_floating_point_sides(direction):
    alpha = 0.04999
    p = float(np.nextafter(alpha, direction))
    displayed = float(_fmt_p_for_alpha(p, alpha))
    assert (displayed < alpha) == (p < alpha)
    assert (displayed > alpha) == (p > alpha)


def test_numeric_boundary_disagreement_is_explained_explicitly():
    res = sw.declare(alpha=0.05, outcome="score", contrast="A minus B").analyze(
        estimate=1.9599639845400545, se=1
    )
    assert not res.evidence.differs_from_zero and res.evidence.p_zero < res.evidence.alpha
    out = res.check("The new method significantly improved scores.", record=False)
    part = _parts(out, "significance")[0]
    assert part.status == "check"
    assert "At numerical precision" in part.reason
    assert "calculated p-value can compare differently" in part.reason
    assert "test-statistic decision" in part.reason


@pytest.mark.xfail(raises=AssertionError, reason="Known pre-existing sentence-wide unbound scope can suppress a later independent test")
@pytest.mark.parametrize("sentence", [
    "Scores increased; this result was statistically significant.",
    "Scores increased; this result's minimal-effect test was significant.",
])
def test_known_unbound_scope_should_not_suppress_later_test_conflict(sentence):
    res = sw.declare(sesoi=1, sesoi_source="example", outcome="score", contrast="A minus B").analyze(
        estimate=0, se=0.5
    )
    out = res.check(sentence, record=False)
    assert [p.status for p in _parts(out, "significance")] == ["conflict"], str(out)


@pytest.mark.xfail(raises=AssertionError, reason="Known pre-existing test-name gap: non-inferiority is not recognised")
def test_known_noninferiority_test_should_not_be_approved_as_zero_test():
    res = sw.declare().analyze(estimate=4, se=1)
    out = res.check("The non-inferiority test was significant.", record=False)
    assert not any(p.status == "consistent" for p in _parts(out, "significance")), str(out)


@pytest.mark.xfail(raises=AssertionError, reason="Known pre-existing significance-to-outcome binding gap")
def test_known_different_outcome_should_not_be_approved_for_significant_result():
    res = sw.declare(outcome="exam score").analyze(estimate=4, se=1)
    out = res.check("The new method significantly improved mortality.", record=False)
    assert not any(p.status == "consistent" for p in _parts(out, "significance")), str(out)


@pytest.mark.xfail(raises=AssertionError, reason="Known pre-existing comparison-binding gap for estimate without contrast")
def test_known_estimate_without_contrast_should_request_binding_review():
    res = _result("estimate")
    out = res.check("The new method significantly improved scores.", record=False)
    assert [p.status for p in _parts(out, "significance")] == ["check"], str(out)


@pytest.mark.xfail(raises=AssertionError, reason="Known pre-existing alpha-level false assurance")
def test_known_stated_alpha_mismatch_should_not_be_marked_consistent():
    res = sw.declare(alpha=0.01).analyze(estimate=2.17, se=1)
    out = res.check("The effect was statistically significant at the 5% level.", record=False)
    assert not any(p.status == "consistent" for p in _parts(out, "alpha-level")), str(out)


@pytest.mark.parametrize("sentence", [
    "The result was significantly positive.",
    "Scores significantly increased because this result was statistically significant.",
    "No SE was given because this result was statistically significant.",
])
def test_affirmative_result_conflicts_are_not_weakened_by_unrelated_context(sentence):
    res = sw.declare().analyze(estimate=0.03, se=0.1)
    out = res.check(sentence, record=False)
    assert out.level == "conflict", str(out)
