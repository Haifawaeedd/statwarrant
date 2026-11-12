"""Regressions from real-data observations; no sentence-wide approval is implied."""
import math

import pytest
import statsmodels.api as sm

import statwarrant as sw


@pytest.fixture(scope="module")
def longley():
    data = sm.datasets.longley.load_pandas().data
    fit = sm.OLS(data["TOTEMP"], sm.add_constant(data.drop(columns=["TOTEMP"]))).fit()
    return sw.declare().analyze(fit, term="UNEMP")


@pytest.mark.parametrize("sentence", [
    "The estimated coefficient was -2.02.",
    "The coefficient was -2.02.",
    "The estimated coefficient was approximately -2.0.",
    "The estimated coefficient was −2.02.",
])
def test_longley_generic_coefficient_and_rounding(longley, sentence):
    assert longley.evidence.estimate == pytest.approx(-2.02022980381683, abs=1e-9)
    result = longley.check(sentence, record=False)
    assert [(p.rule, p.status) for p in result.parts] == [("reported-number", "consistent")]
    assert "not a clearance" in str(result)


@pytest.mark.parametrize("sentence,level", [
    ("The estimated coefficient was 2.02.", "conflict"),
    ("The estimated coefficient was -2.03.", "check"),  # inside the CI, but not the rounded estimate
    ("The estimated coefficient was -8.00.", "conflict"),
    ("The estimated coefficient was 2.02, and the effect was negative.", "conflict"),
])
def test_longley_wrong_number_or_sign_warns(longley, sentence, level):
    result = longley.check(sentence, record=False)
    assert result.level == level
    assert not any(p.rule == "reported-number" and p.status == "consistent" for p in result.parts)


@pytest.mark.parametrize("sentence", [
    "The weight coefficient was -2.02.",
    "The other estimated coefficient was -2.02.",
    "The estimated coefficient was -2.02 for weight.",
    "The estimated coefficient was -2.02 mpg for weight.",
    "The estimated coefficient was -2.02, corresponding to weight.",
    "The estimated coefficient was -2.02 (weight).",
    "The estimated coefficient was -2.02 in the weight model.",
    "The estimated coefficient was -2.02 with adjustment for weight.",
    "The coefficient for weight was -2.02.",
    "The temperature was -2.02.",
    "The sample had 3333333333333333333333333333 observations.",
])
def test_ambiguous_term_or_unrelated_number_not_accepted(longley, sentence):
    result = longley.check(sentence, record=False)
    assert result.level == "check"
    assert any(p.rule == "unverified-number" for p in result.warnings)
    assert not any(p.rule == "reported-number" and p.status == "consistent" for p in result.parts)


def test_other_coefficient_not_bound_to_first(longley):
    sentence = "The estimated coefficient was -2.02; the other coefficient was -2.02."
    result = longley.check(sentence, record=False)
    assert [(p.rule, p.status) for p in result.parts] == [
        ("reported-number", "consistent"), ("unverified-number", "check")]


def test_coefficient_match_does_not_clear_unrelated_words(longley):
    result = longley.check("The estimated coefficient was -2.02 and the model is flawless.", record=False)
    assert any("flawless" in text for text in result.unchecked)
    assert "not a clearance" in str(result)


@pytest.fixture(scope="module")
def toothgrowth():
    # Fixed summary for ToothGrowth, dose 1 mg/day: OJ minus VC, Welch t test.
    # The SESOI is illustrative, and this test does not refit the raw data.
    # https://stat.ethz.ch/R-manual/R-devel/library/datasets/html/ToothGrowth.html
    return sw.declare(sesoi=5, sesoi_source="illustrative", units="units").analyze(
        estimate=5.929999999999996, se=1.4704534448031104, df=15.357671628182151)


def test_toothgrowth_neither_nor_is_safely_downgraded(toothgrowth):
    assert toothgrowth.evidence.estimate == pytest.approx(5.93)
    assert not toothgrowth.evidence.equivalent and not toothgrowth.evidence.exceeds_sesoi
    sentence = ("The estimated difference was 5.93 units, but the evidence established neither "
                "equivalence within plus or minus 5 units nor an effect exceeding 5 units in magnitude.")
    result = toothgrowth.check(sentence, record=False)
    assert result.level == "check"
    assert any(p.rule == "neither-equivalence" and p.status == "check" for p in result.parts)
    assert not any(p.rule in ("no-effect", "equivalence") for p in result.parts)
    assert not any(p.rule == "neither-equivalence" and p.status == "consistent" for p in result.parts)
    assert "has not been verified" in str(result)


def test_unsupported_positive_equivalence_remains_conflict(toothgrowth):
    result = toothgrowth.check(
        "The evidence established equivalence within plus or minus 5 units and an effect exceeding 5 units in magnitude.",
        record=False)
    assert any(p.rule == "equivalence" and p.status == "conflict" for p in result.parts)


@pytest.mark.parametrize("estimate,se", [(0.02, 0.05), (0.6, 0.1)])
def test_neither_claim_is_not_falsely_marked_consistent_if_evidence_differs(estimate, se):
    result = sw.declare(sesoi=0.2, sesoi_source="illustrative").analyze(estimate=estimate, se=se)
    out = result.check("The evidence established neither equivalence nor an effect.", record=False)
    assert out.level == "check"
    assert any(p.rule == "neither-equivalence" and p.status == "check" for p in out.parts)


def test_literal_no_effect_remains_conflict(toothgrowth):
    assert toothgrowth.check("There was no effect.", record=False).level == "conflict"


@pytest.mark.parametrize("sesoi,estimate,se", [
    (None, 0.6, 0.1), (0.2, 0.6, 0.1), (0.2, 0.3, 0.1),
    (0.2, 0.02, 0.05), (0.2, 0.15, 0.2),
])
def test_large_needs_defined_scale_regardless_of_sesoi(sesoi, estimate, se):
    plan = sw.declare() if sesoi is None else sw.declare(sesoi=sesoi, sesoi_source="illustrative")
    result = plan.analyze(estimate=estimate, se=se).check("The effect was large.", record=False)
    assert result.level == "check"
    reason = next(p.reason for p in result.parts if p.rule == "big")
    assert "does not define 'large'" in reason
    assert "significance alone does not establish practical importance" in reason


def test_large_opposite_direction_still_conflicts():
    result = sw.declare(sesoi=0.2, sesoi_source="illustrative").analyze(estimate=0.6, se=0.1)
    assert result.check("The program produced a large decrease.", record=False).level == "conflict"


@pytest.mark.parametrize("baseline,sign", [(1e-307, "+"), (-1e-307, "-")])
def test_extreme_finite_relative_percent_never_prints_inf(baseline, sign):
    result = sw.declare().analyze(estimate=1.0, se=0.1, baseline=baseline)
    assert math.isfinite(result.to_dict()["reporting"]["relative_change"])
    note = result.claims.notes[-1]
    assert f"{sign}1.00e+309%" in note
    assert "inf%" not in note.lower()
    result.to_json()
    for sentence in ("The effect was 1%.", "The effect was 50%."):
        out = str(result.check(sentence, record=False))
        assert "inf%" not in out.lower()
        assert "e+30" in out


def test_ordinary_relative_percent_format_is_unchanged():
    result = sw.declare().analyze(estimate=1.0, se=0.1, baseline=5.0)
    assert "+20.0%" in result.claims.notes[-1]
    assert "+20.0%" in str(result.check("The effect was 20%.", record=False))
