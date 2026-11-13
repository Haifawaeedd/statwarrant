"""Review regressions for shared log-scale safety, not an accuracy benchmark."""

import math

import pytest

import statwarrant as sw


@pytest.mark.parametrize("units", ["logit_p", "logit_probability", "logitP"])
@pytest.mark.parametrize("route", ["estimate", "interval", "paired"])
def test_logit_prefix_never_divides_transformed_result_by_baseline(units, route):
    plan = sw.declare(units=units)
    with pytest.raises(ValueError, match="baseline.*log-scale"):
        if route == "estimate":
            plan.analyze(estimate=-0.2, se=0.05, baseline=0.2)
        elif route == "interval":
            plan.analyze(ci=(-0.3, -0.1), baseline=0.2)
        else:
            plan.analyze_paired([0.1, 0.2, 0.3, 0.4], [0., 0., 0., 0.], baseline=0.2)


@pytest.mark.parametrize("units", [
    "log base 2 risk ratio", "log2 risk ratio", "log_2 risk ratio", "log₂ risk ratio",
    "log base 10 risk ratio", "log10 risk ratio", "base10 log risk ratio",
    "log base b risk ratio", "common log risk ratio", "binary log risk ratio", "logit_p base 2 odds ratio",
])
def test_ratio_input_rejects_non_natural_or_ambiguous_declared_base(units):
    # SESOI is expressed in the stated units: interpreting it on ln instead
    # of log2 can change the decision. Never silently substitute scales.
    plan = sw.declare(sesoi=0.09, sesoi_source="illustrative threshold", units=units)
    with pytest.raises(ValueError, match="natural logarithm"):
        plan.analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)


@pytest.mark.parametrize("units", ["log risk ratio", "natural log risk ratio", "ln risk ratio",
                                    "logit_p", "logit_probability", "logitP", "natural logit_p odds ratio"])
def test_ratio_input_with_natural_log_units_preserves_expected_evidence(units):
    plan = sw.declare(sesoi=0.09, sesoi_source="illustrative threshold", units=units)
    result = plan.analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)
    assert result.evidence.estimate == pytest.approx((math.log(.75) + math.log(.93)) / 2)
    assert not result.evidence.exceeds_sesoi


@pytest.mark.parametrize("units", ["logit_p", "logit_probability", "logitP", "natural logit_p odds ratio"])
def test_logit_argument_is_not_mistaken_for_a_log_base(units):
    result = sw.declare(units=units).analyze(estimate=-1, se=.05)
    checked = result.check("The odds of failure halved.", record=False)
    assert any(p.rule == "ratio" and p.status == "conflict" and "0.368" in p.reason for p in checked.parts)


@pytest.mark.parametrize("units", [
    "log base 2 risk ratio", "log risk ratio", "logit probability", "risk ratio", "rate ratio",
])
def test_percentage_points_not_converted_to_log_or_ratio_scale(units):
    result = sw.declare(units=units).analyze(estimate=-.5, se=.05)
    checked = result.check("The difference was 29.3 percentage points.", record=False)
    parts = [p for p in checked.parts if p.rule == "reported-number"]
    assert parts and all(p.status == "check" for p in parts)
    assert not any(p.status == "conflict" for p in parts)


def test_percentage_points_still_convert_for_an_ordinary_proportion():
    result = sw.declare(units="accuracy").analyze(estimate=.009, se=.002)
    checked = result.check("The difference was 0.9 percentage points.", record=False)
    assert any(p.rule == "reported-number" and p.status == "consistent" for p in checked.parts)
