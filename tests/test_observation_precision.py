"""Regressions for silent integer narrowing at the public inference boundaries."""
from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw


N = 2**53
LOSSY = N + 1
EXACT = N + 2


@pytest.mark.parametrize("value", [
    LOSSY, np.int64(LOSSY), np.uint64(LOSSY), Decimal(str(LOSSY)),
    Decimal(str(LOSSY) + ".0"), Fraction(LOSSY, 1), np.array(LOSSY),
])
def test_scalar_sesoi_rejects_nonrepresentable_integer(value):
    with pytest.raises(ValueError, match="sesoi.*integer.*exactly.*float"):
        sw.declare(sesoi=value, sesoi_source="x")


def test_user_fixture_is_refused_before_false_inference():
    # The old code rounded N+1 down to N, then incorrectly declared the effect exceeds it.
    with pytest.raises(ValueError, match="sesoi.*exactly"):
        sw.declare(sesoi=N + 1, sesoi_source="x").analyze(estimate=N + 2, se=.6)

    # A float supplied already rounded cannot convey the originally intended N+1.
    rounded = float(N + 1)
    assert rounded == float(N)
    result = sw.declare(sesoi=rounded, sesoi_source="x").analyze(estimate=N + 2, se=.6)
    assert result.plan.sesoi == (-float(N), float(N))
    assert result.evidence.exceeds_sesoi


@pytest.mark.parametrize("bounds,field", [
    ((-LOSSY, 1), "lower"),
    ((-1, LOSSY), "upper"),
    ((Decimal(str(-LOSSY)), np.int64(2)), "lower"),
    ((np.int64(-2), Decimal(str(LOSSY))), "upper"),
    ((-1, str(LOSSY)), "upper"),
])
def test_asymmetric_sesoi_bounds_refuse_lossy_integer(bounds, field):
    with pytest.raises(ValueError, match="sesoi " + field + ".*exactly"):
        sw.declare(sesoi=bounds, sesoi_source="x")


@pytest.mark.parametrize("value", [LOSSY, -LOSSY, np.int64(LOSSY), np.uint64(LOSSY),
                                    Decimal(str(LOSSY)), Fraction(LOSSY, 1), str(LOSSY),
                                    np.array(LOSSY)])
@pytest.mark.parametrize("field", ["estimate", "baseline", "se", "df"])
def test_explicit_inputs_refuse_lossy_integers(value, field):
    args = {"estimate": 1, "se": 1}
    args[field] = value
    with pytest.raises(ValueError, match=field + ".*exactly.*float"):
        sw.declare().analyze(**args)


@pytest.mark.parametrize("ci,field", [
    ((-LOSSY, 1), "lower"),
    ((-1, LOSSY), "upper"),
    ((Decimal(str(-LOSSY)), 1), "lower"),
    ((-1, np.uint64(LOSSY)), "upper"),
    ((-1, str(LOSSY)), "upper"),
])
def test_ci_bounds_refuse_lossy_integer(ci, field):
    with pytest.raises(ValueError, match="ci " + field + ".*exactly"):
        sw.declare().analyze(ci=ci)


def test_estimate_with_ci_is_checked_before_midpoint_comparison():
    with pytest.raises(ValueError, match="estimate.*exactly"):
        sw.declare().analyze(estimate=LOSSY, ci=(-1, 1))


def test_baseline_is_checked_for_paired_and_fitted_results():
    plan = sw.declare()
    with pytest.raises(ValueError, match="baseline.*exactly"):
        plan.analyze_paired([1, 2, 4], [0, 0, 0], baseline=LOSSY)
    fit = stats.ttest_1samp([1, 2, 4], 0)
    with pytest.raises(ValueError, match="baseline.*exactly"):
        plan.analyze(fit, baseline=Decimal(str(LOSSY)))


def test_public_evaluate_and_threshold_decision_refuse_lossy_values():
    with pytest.raises(ValueError, match="estimate.*exactly"):
        sw.evaluate(LOSSY, .6, None, .05, "single", (-1., float(EXACT)))
    with pytest.raises(ValueError, match="sesoi upper bound.*exactly"):
        sw.evaluate(EXACT, .6, None, .05, "single", (-1., LOSSY))
    result = sw.declare().analyze(estimate=EXACT, se=.6)
    with pytest.raises(ValueError, match="threshold.*exactly"):
        result.thresholds.decision(LOSSY)


@pytest.mark.parametrize("value", [10**400, -(10**400), Decimal("1e400"), "1e400"])
def test_enormous_explicit_integers_fail_with_clear_error(value):
    with pytest.raises(ValueError, match="(estimate|finite float)"):
        sw.declare().analyze(estimate=value, se=1)
    with pytest.raises(ValueError, match="(baseline|finite float)"):
        sw.declare().analyze(estimate=1, se=1, baseline=value)
    with pytest.raises(ValueError, match="(ci upper|finite float)"):
        sw.declare().analyze(ci=(-1, value))


def test_enormous_scalar_and_bound_have_clear_overflow_errors():
    with pytest.raises(ValueError, match="sesoi.*finite float"):
        sw.declare(sesoi=10**400, sesoi_source="x")
    with pytest.raises(ValueError, match="sesoi lower bound.*finite float"):
        sw.declare(sesoi=(-(10**400), 1), sesoi_source="x")


def test_exactly_representable_large_integers_remain_usable():
    for value in (N, EXACT, 2**100, Decimal(str(EXACT)), np.int64(EXACT)):
        plan = sw.declare(sesoi=value, sesoi_source="x")
        assert plan.sesoi == (-float(value), float(value))
    result = sw.declare(sesoi=(np.int64(-3), Decimal("2")), sesoi_source="x").analyze(
        estimate=np.int64(4), se=Decimal("0.6"), df=np.int64(20), baseline=Decimal("100"))
    assert result.evidence.estimate == 4
    assert result.context.baseline == 100
    assert result.evidence.exceeds_sesoi
    assert sw.declare().analyze(estimate=EXACT, se=1, baseline=EXACT).context.baseline == float(EXACT)


def test_ordinary_fractional_values_and_ci_are_still_accepted():
    plan = sw.declare(sesoi=Decimal("0.1"), sesoi_source="x")
    result = plan.analyze(estimate=Decimal("0.3"), se=Fraction(1, 20), baseline=Decimal("3.1"))
    assert result.plan.sesoi == (-0.1, 0.1)
    assert result.evidence.estimate == 0.3
    assert result.context.baseline == 3.1
    interval = sw.declare(sesoi=(Decimal("-0.4"), np.float32(0.5)), sesoi_source="x").analyze(
        estimate=Decimal("0.2"), ci=(Decimal("-0.1"), Decimal("0.5")))
    assert interval.evidence.estimate == pytest.approx(0.2)
    assert interval.raw_input["ci"] == [-0.1, 0.5]


def test_extended_precision_integral_scalar_is_not_silently_narrowed():
    value = np.longdouble(str(LOSSY))
    if int(value) != LOSSY:
        pytest.skip("longdouble has no extra integer precision on this platform")
    with pytest.raises(ValueError, match="sesoi.*exactly"):
        sw.declare(sesoi=value, sesoi_source="x")
    with pytest.raises(ValueError, match="estimate.*exactly"):
        sw.declare().analyze(estimate=value, se=1)
