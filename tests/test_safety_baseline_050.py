"""Baseline validation for declared transformed results across public routes."""

import math

import pytest
from scipy import stats

import statwarrant as sw


# This reproduces the review's paired example: these are synthetic data, not
# an arithmetic-risk estimate. Dividing their log difference by .2 is invalid.
B = [math.log(0.2)] * 20
DIFFERENCES = [-0.19, -0.20, -0.21, -0.20] * 5
A = [b + d for b, d in zip(B, DIFFERENCES)]
CLUSTERS = [i // 2 for i in range(len(A))]


class ModelResult:
    """A minimal fitted-result adapter input with one named coefficient."""
    params = {"effect": -0.2}
    bse = {"effect": 0.05}
    use_t = False
    tvalues = {"effect": -4.0}
    pvalues = {"effect": 2 * stats.norm.sf(4.0)}


def _analyze(plan, route, baseline):
    if route == "estimate-se":
        return plan.analyze(estimate=-0.2, se=0.05, baseline=baseline)
    if route == "interval":
        return plan.analyze(ci=(-0.3, -0.1), baseline=baseline)
    if route == "scipy":
        return plan.analyze(stats.ttest_1samp(DIFFERENCES, 0), baseline=baseline)
    if route == "fitted":
        return plan.analyze(ModelResult(), term="effect", baseline=baseline)
    if route == "paired":
        return plan.analyze_paired(A, B, baseline=baseline)
    if route == "paired-clustered":
        return plan.analyze_paired(A, B, cluster=CLUSTERS, baseline=baseline)
    raise AssertionError(route)


ROUTES = ["estimate-se", "interval", "scipy", "fitted", "paired", "paired-clustered"]
LOG_UNITS = [
    "log risk ratio", "log-odds", "LOG HAZARD RATIO", "logit", "logits",
    "logit(p)", "logit_p", "logit_probability", "logitP", "logarithm of the risk ratio", "logarithmic scale",
    "ln(rate ratio)", "ln(p)", "lnRR", "lnOR", "lnHR", "lnIRR", "ln_RR",
    "logRR", "logOR", "logHR", "logIRR", "lnRiskRatio", "logOddsRatio",
    "log_risk_ratio", "ln_odds_ratio",
    "log2 risk ratio", "LOG10 risk ratio", "log2(RR)", "log10(RR)",
    "log_2 risk ratio", "log_10 risk ratio", "log₂ risk ratio", "log₁₀ risk ratio",
    "log2RR", "log10OR", "log2FC", "log2_fold_change", "log base 2 risk ratio",
]


@pytest.mark.parametrize("units", LOG_UNITS)
@pytest.mark.parametrize("route", ROUTES)
def test_declared_log_baseline_is_rejected_on_each_route(units, route):
    with pytest.raises(ValueError, match="baseline.*log-scale") as exc:
        _analyze(sw.declare(units=units), route, 0.2)
    assert "Omit baseline=" in str(exc.value)
    # The explanation must not assert that an arbitrary log value is a ratio.
    assert "a log-scale value is not necessarily a ratio" in str(exc.value)


def test_review_example_does_not_divide_paired_log_difference_by_baseline():
    plan = sw.declare(units="log risk ratio")
    unbased = plan.analyze_paired(A, B)
    assert unbased.evidence.estimate == pytest.approx(-0.2)
    assert "reporting" not in unbased.to_dict()
    assert math.expm1(unbased.evidence.estimate) == pytest.approx(-0.1812692469220181)
    with pytest.raises(ValueError, match="baseline.*log-scale"):
        plan.analyze_paired(A, B, baseline=0.2)


@pytest.mark.parametrize("units", ["logit(p)", "log2 risk ratio", "log10 risk ratio", "lnRR"])
@pytest.mark.parametrize("route", ROUTES)
def test_log_results_remain_usable_without_a_baseline(units, route):
    result = _analyze(sw.declare(units=units), route, None)
    assert result.evidence.estimate == pytest.approx(-0.2)
    assert result.context.baseline is None
    assert "reporting" not in result.to_dict()


def test_all_routes_give_the_same_scale_error_for_the_same_units():
    messages = []
    for route in ROUTES:
        with pytest.raises(ValueError) as exc:
            _analyze(sw.declare(units="log2 risk ratio"), route, 0.2)
        messages.append(str(exc.value))
    assert len(set(messages)) == 1


@pytest.mark.parametrize("units", [None, "points", "mmHg", "kg", "cases", "blog visits",
                                    "logins per day", "log-in attempts", "log in events",
                                    "logistic regression scores", "logitech devices", "catalogue sales"])
@pytest.mark.parametrize("route", ROUTES)
def test_linear_baselines_and_non_log_words_are_not_rejected(units, route):
    result = _analyze(sw.declare(units=units), route, 40.0)
    reporting = result.to_dict()["reporting"]
    assert reporting["baseline"] == 40.0
    assert reporting["absolute_change"] == pytest.approx(-0.2)
    assert reporting["relative_change"] == pytest.approx(-0.005)
    assert result.context.baseline == 40.0


@pytest.mark.parametrize("units", [None, "points", "risk ratio", "log2 risk ratio"])
def test_explicit_ratio_with_baseline_is_rejected_even_for_linear_units(units):
    with pytest.raises(ValueError, match="baseline.*ratio"):
        sw.declare(units=units).analyze(estimate=0.83, ci=(0.75, 0.93),
                                        ratio=True, baseline=0.2)


def test_ratio_without_baseline_still_reports_and_preserves_scale_warning():
    result = sw.declare(units="risk ratio").analyze(
        estimate=0.83, ci=(0.75, 0.93), ratio=True)
    notes = result.raw_input["provenance_notes"]
    assert any("On the ratio scale" in note for note in notes)
    # The untransformed declared label must receive the natural-log warning.
    assert any("log ratios" in note for note in notes)
    assert "reporting" not in result.to_dict()


@pytest.mark.parametrize("baseline", [0.0, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("route", ["estimate-se", "paired", "paired-clustered"])
def test_invalid_linear_baseline_is_still_rejected(baseline, route):
    with pytest.raises(ValueError, match="baseline"):
        _analyze(sw.declare(units="points"), route, baseline)


@pytest.mark.parametrize("route", ["estimate-se", "paired", "paired-clustered"])
def test_negative_linear_baseline_retains_existing_arithmetic(route):
    result = _analyze(sw.declare(units="points"), route, -40.0)
    assert result.to_dict()["reporting"]["relative_change"] == pytest.approx(0.005)
