"""Regression coverage for thresholds over the positive binary64 domain."""

import json
import math
import sys

import pytest
from hypothesis import given, settings, strategies as st
from scipy import stats

import statwarrant as sw
from statwarrant._core import Thresholds, evaluate


MIN_POSITIVE = math.nextafter(0.0, math.inf)
MAX_FINITE = sys.float_info.max


def assert_boundaries(th):
    """Check both adjacent transitions, including the finite-domain endpoints."""
    met = th.met_below
    eq = th.equivalence_above
    assert math.isfinite(eq) and 0 <= eq <= MAX_FINITE
    if met is None:
        assert th.decision(MIN_POSITIVE) != "exceeds"
    else:
        assert math.isfinite(met) and MIN_POSITIVE <= met <= eq
        assert th.decision(met) == "undetermined"
        lower = math.nextafter(met, 0.0)
        if lower > 0:
            assert th.decision(lower) == "exceeds"
    if eq > 0:
        assert th.decision(eq) == "undetermined"
    higher = math.nextafter(eq, math.inf)
    if math.isfinite(higher):
        assert th.decision(higher) == "equivalent"


def assert_positions(th, positions):
    """All sampled positions must agree with the strict displayed cutoffs."""
    for d in positions:
        if not (math.isfinite(d) and d > 0):
            continue
        if th.met_below is not None and d < th.met_below:
            expected = "exceeds"
        elif d > th.equivalence_above:
            expected = "equivalent"
        else:
            expected = "undetermined"
        assert th.decision(d) == expected, (th, d, expected)


@pytest.mark.parametrize("sign", [-1.0, 1.0])
@pytest.mark.parametrize("policy", ["single", "standard"])
@pytest.mark.parametrize("scale", [2.0**-500, 1.0, 2.0**500])
def test_near_cancellation_report_and_decision_agree(sign, policy, scale):
    critical = float(stats.norm.isf(0.025))
    estimate = sign * math.nextafter(critical * scale, math.inf)
    declared = 2e-16 * scale
    result = sw.declare(sesoi=declared, sesoi_source="regression", interval_policy=policy).analyze(
        estimate=estimate, se=scale
    )
    th = result.thresholds
    assert result.evidence.differs_from_zero
    assert not result.evidence.exceeds_sesoi
    assert th.decision(declared) == "undetermined"
    assert th.met_below is not None and 0 < th.met_below <= declared
    assert_boundaries(th)
    # The conservatively rounded, printed lower cutoff cannot include the declared d.
    printed_lower = float(result._threshold_lines()[0].split("**")[1])
    assert printed_lower <= th.met_below <= declared
    assert "neither is established" in result._threshold_lines()[-1]
    assert json.loads(result.to_json())["thresholds"]["declared_threshold"] == "undetermined"
    assert "Every threshold at once" in result.to_markdown()


def test_search_is_bounded_and_never_asks_about_zero_or_infinity(monkeypatch):
    critical = float(stats.norm.isf(0.025))
    ev = evaluate(math.nextafter(critical, math.inf), 1.0, None, 0.05, "single", None)
    original = Thresholds.decision
    calls = []

    def record(self, d):
        assert math.isfinite(d) and d > 0
        calls.append(d)
        return original(self, d)

    monkeypatch.setattr(Thresholds, "decision", record)
    th = ev.thresholds()
    # Two searches of at most 63 iterations, plus at most two fast-path probes each.
    assert len(calls) <= 130
    assert_boundaries(th)


def test_maximum_finite_interval_exports_without_a_successor():
    critical = float(stats.norm.isf(0.025))
    result = sw.declare().analyze(estimate=0.0, se=MAX_FINITE / critical)
    assert result.evidence.zero_interval == (-MAX_FINITE, MAX_FINITE)
    th = result.thresholds
    assert th.met_below is None
    assert th.equivalence_above == MAX_FINITE
    assert_boundaries(th)
    assert th.decision(MAX_FINITE) == "undetermined"
    assert json.loads(result.to_json())["thresholds"]["equivalence_above"] == MAX_FINITE
    assert "Every threshold at once" in result.to_markdown()
    assert "Every threshold" in str(result)


@pytest.mark.parametrize("sign", [-1.0, 1.0])
@pytest.mark.parametrize("policy", ["single", "standard"])
def test_maximum_estimate_and_smallest_se_export(sign, policy):
    result = sw.declare(interval_policy=policy).analyze(
        estimate=sign * MAX_FINITE, se=MIN_POSITIVE
    )
    th = result.thresholds
    assert th.met_below == th.equivalence_above == MAX_FINITE
    assert_boundaries(th)
    assert th.decision(math.nextafter(MAX_FINITE, 0.0)) == "exceeds"
    assert json.loads(result.to_json())["thresholds"]["met_below"] == MAX_FINITE
    assert "Every threshold at once" in result.to_markdown()


@pytest.mark.parametrize("sign", [-1.0, 1.0])
def test_none_when_zero_test_is_not_established_at_cancellation(sign):
    # Rounded interval subtraction and test-statistic division can disagree on
    # the side of zero. The latter controls decisions and the None case.
    result = sw.declare().analyze(estimate=sign * 127.73562964352773, se=65.17243717287157)
    assert not result.evidence.differs_from_zero
    th = result.thresholds
    assert th.met_below is None
    assert_boundaries(th)
    assert_positions(th, [MIN_POSITIVE, 1e-14, 1.0, MAX_FINITE])


def test_zero_cutoff_when_every_positive_float_is_equivalent():
    result = sw.declare(alpha=0.4, interval_policy="standard").analyze(
        estimate=0.0, se=MIN_POSITIVE
    )
    th = result.thresholds
    assert th.met_below is None and th.equivalence_above == 0.0
    assert_boundaries(th)
    assert th.decision(MIN_POSITIVE) == "equivalent"
    with pytest.raises(ValueError):
        th.decision(0.0)
    assert json.loads(result.to_json())["thresholds"]["equivalence_above"] == 0.0
    assert "Every threshold at once" in result.to_markdown()


@pytest.mark.parametrize("sign", [-1.0, 1.0])
def test_zero_test_can_succeed_but_no_positive_threshold_exceeds(sign):
    result = sw.declare(alpha=0.49, interval_policy="standard").analyze(
        estimate=sign * MIN_POSITIVE, se=MIN_POSITIVE
    )
    assert result.evidence.differs_from_zero
    th = result.thresholds
    # The lower open region contains no positive binary64 value.
    assert th.met_below == MIN_POSITIVE
    assert th.decision(MIN_POSITIVE) == "undetermined"
    assert_boundaries(th)
    assert json.loads(result.to_json())["thresholds"]["met_below"] == MIN_POSITIVE
    result.to_markdown()


@pytest.mark.parametrize("d", [0.0, -0.0, -1.0, math.inf, -math.inf, math.nan])
def test_decision_rejects_thresholds_outside_positive_finite_domain(d):
    th = evaluate(0.0, 1.0, None, 0.05, "single", None).thresholds()
    with pytest.raises(ValueError):
        th.decision(d)


@settings(max_examples=350, deadline=None, derandomize=True)
@given(
    sign=st.sampled_from([-1.0, 0.0, 1.0]),
    exponent=st.integers(min_value=-1074, max_value=1019),
    ratio=st.sampled_from([0.0, 0.125, 0.5, 1.0, 1.9599639845400545, 2.0, 8.0]),
    alpha=st.sampled_from([0.05, 0.2, 0.49]),
    df=st.sampled_from([None, 3.0, 20.0]),
    policy=st.sampled_from(["single", "standard"]),
)
def test_boundary_properties_across_exponents_and_policies(sign, exponent, ratio, alpha, df, policy):
    se = math.ldexp(1.0, exponent)
    estimate = sign * ratio * se
    th = evaluate(estimate, se, df, alpha, policy, None).thresholds()
    assert_boundaries(th)
    probes = [MIN_POSITIVE, MAX_FINITE, se, abs(estimate), th.equivalence_above]
    if th.met_below is not None:
        probes.extend([th.met_below, math.nextafter(th.met_below, 0.0),
                       math.nextafter(th.met_below, math.inf)])
    probes.extend([math.nextafter(th.equivalence_above, 0.0),
                   math.nextafter(th.equivalence_above, math.inf)])
    assert_positions(th, probes)


@settings(max_examples=200, deadline=None, derandomize=True)
@given(
    estimate=st.floats(min_value=-1e5, max_value=1e5, allow_nan=False, allow_infinity=False),
    se=st.floats(min_value=1e-5, max_value=1e4, allow_nan=False, allow_infinity=False),
    d=st.floats(min_value=1e-7, max_value=1e6, allow_nan=False, allow_infinity=False),
    df=st.sampled_from([None, 3.0, 58.0]),
    policy=st.sampled_from(["single", "standard"]),
)
def test_decision_matches_evidence_for_symmetric_declared_bounds(estimate, se, d, df, policy):
    ev = evaluate(estimate, se, df, 0.05, policy, (-d, d))
    th = ev.thresholds()
    expected = "exceeds" if ev.exceeds_sesoi else "equivalent" if ev.equivalent else "undetermined"
    assert th.decision(d) == expected
    assert_boundaries(th)
    assert_positions(th, [d])
