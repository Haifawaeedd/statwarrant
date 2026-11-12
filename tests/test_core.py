import math

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant._core import evaluate

sm_weightstats = pytest.importorskip("statsmodels.stats.weightstats")


def pooled(x1, x2):
    n1, n2 = len(x1), len(x2)
    sp2 = ((n1 - 1) * np.var(x1, ddof=1) + (n2 - 1) * np.var(x2, ddof=1)) / (n1 + n2 - 2)
    return x1.mean() - x2.mean(), math.sqrt(sp2 * (1 / n1 + 1 / n2)), n1 + n2 - 2


@pytest.mark.parametrize("seed", range(40))
def test_tost_and_met_match_statsmodels(seed):
    rng = np.random.default_rng(seed)
    n1, n2 = rng.integers(5, 60, size=2)
    x1 = rng.normal(rng.normal(0, 0.5), 1, n1)
    x2 = rng.normal(0, 1, n2)
    low, high = -rng.uniform(0.1, 1), rng.uniform(0.1, 1)
    est, se, df = pooled(x1, x2)
    ev = evaluate(est, se, df, 0.05, "standard", (low, high))

    p, lower, upper = sm_weightstats.ttost_ind(x1, x2, low, high, usevar="pooled")
    pv1, pv2 = lower[1], upper[1]
    assert ev.p_equivalence == pytest.approx(p, abs=1e-10)
    assert ev.p_minimal_effect == pytest.approx(min(1 - pv1, 1 - pv2), abs=1e-10)


@pytest.mark.parametrize("seed", range(40))
def test_zero_test_and_interval_match_scipy(seed):
    rng = np.random.default_rng(100 + seed)
    x1 = rng.normal(0.3, 1, rng.integers(5, 50))
    x2 = rng.normal(0, 1, rng.integers(5, 50))
    est, se, df = pooled(x1, x2)
    ev = evaluate(est, se, df, 0.05, "single", None)
    ref = stats.ttest_ind(x1, x2)
    ci = ref.confidence_interval(0.95)
    assert ev.p_zero == pytest.approx(ref.pvalue, rel=1e-9)
    assert ev.zero_interval[0] == pytest.approx(ci.low, rel=1e-9)
    assert ev.zero_interval[1] == pytest.approx(ci.high, rel=1e-9)


@pytest.mark.parametrize("policy,eq_threshold", [("standard", 0.05), ("single", 0.025)])
@pytest.mark.parametrize("seed", range(30))
def test_decisions_equal_pvalue_rules(policy, eq_threshold, seed):
    rng = np.random.default_rng(200 + seed)
    est, se = rng.normal(0, 0.5), rng.uniform(0.05, 0.5)
    low, high = -rng.uniform(0.05, 1), rng.uniform(0.05, 1)
    ev = evaluate(est, se, None, 0.05, policy, (low, high))
    assert ev.equivalence_threshold == eq_threshold
    assert ev.met_threshold == 0.025  # the minimal-effect test splits alpha over two directions
    assert ev.equivalent == (ev.p_equivalence < eq_threshold)
    assert ev.exceeds_sesoi == (ev.p_minimal_effect < 0.025)
    assert ev.differs_from_zero == (ev.p_zero < 0.05)


def test_single_policy_uses_one_interval():
    ev = evaluate(0.3, 0.1, None, 0.05, "single", (-0.2, 0.2))
    assert ev.equivalence_interval == pytest.approx(ev.zero_interval)
    assert ev.met_interval == pytest.approx(ev.zero_interval)
    assert ev.equivalence_level == pytest.approx(0.95)


def test_standard_policy_changes_only_the_equivalence_interval():
    ev = evaluate(0.3, 0.1, None, 0.05, "standard", (-0.2, 0.2))
    assert ev.equivalence_level == pytest.approx(0.90)
    assert ev.met_level == pytest.approx(0.95)
    assert ev.met_interval == pytest.approx(ev.zero_interval)


def test_t_distribution_is_used_when_df_given():
    ev_t = evaluate(1.0, 0.5, 5, 0.05, "single", None)
    ev_z = evaluate(1.0, 0.5, None, 0.05, "single", None)
    assert ev_t.zero_interval[1] - ev_t.zero_interval[0] > ev_z.zero_interval[1] - ev_z.zero_interval[0]


@pytest.mark.parametrize("kwargs", [
    dict(estimate=float("nan"), se=1.0),
    dict(estimate=1.0, se=0.0),
    dict(estimate=1.0, se=-1.0),
    dict(estimate=1.0, se=1.0, df=float("nan")),
    dict(estimate=1.0, se=1.0, df=0),
    dict(estimate=1.0, se=1.0, sesoi=(float("-inf"), float("inf"))),
    dict(estimate=1.0, se=1.0, sesoi=(-1.0, float("nan"))),
])
def test_bad_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        evaluate(kwargs["estimate"], kwargs["se"], kwargs.get("df"), 0.05, "single", kwargs.get("sesoi"))


def test_declare_validation():
    with pytest.raises(ValueError, match="reason"):
        sw.declare(sesoi=0.2)
    with pytest.raises(ValueError):
        sw.declare(sesoi=(0.1, 0.3), sesoi_source="x")
    with pytest.raises(ValueError):
        sw.declare(sesoi=-1, sesoi_source="x")
    with pytest.raises(ValueError):
        sw.declare(sesoi=float("inf"), sesoi_source="x")
    with pytest.raises(ValueError):
        sw.declare(sesoi=(float("-inf"), float("inf")), sesoi_source="x")
    with pytest.raises(ValueError):
        sw.declare(interval_policy="loose")
    with pytest.raises(ValueError):
        sw.declare(better="bigger")
    plan = sw.declare(sesoi=0.2, sesoi_source="x")
    assert plan.sesoi == (-0.2, 0.2)
    assert plan.interval_policy == "single"


def test_analyze_needs_exactly_one_input():
    plan = sw.declare()
    with pytest.raises(ValueError):
        plan.analyze()
    with pytest.raises(ValueError):
        plan.analyze(estimate=1, se=1, ci=(0, 2))
    with pytest.raises(ValueError):
        plan.analyze(se=1)


# Critical thresholds: one reading of the intervals must reproduce evaluate() for every threshold.
from hypothesis import given, settings, strategies as st  # noqa: E402


@settings(max_examples=400, deadline=None)
@given(
    est=st.floats(-5, 5, allow_nan=False),
    se=st.floats(0.05, 3, allow_nan=False),
    d=st.floats(0.01, 20, allow_nan=False),
    df=st.one_of(st.none(), st.floats(2, 200)),
    policy=st.sampled_from(["single", "standard"]),
)
def test_thresholds_reproduce_evaluate(est, se, d, df, policy):
    ev = evaluate(est, se, df, 0.05, policy, (-d, d))
    th = evaluate(est, se, df, 0.05, policy, None).thresholds()
    edges = [x for x in (th.met_below, th.equivalence_above) if x is not None]
    if any(abs(d - x) < 1e-9 for x in edges):
        return  # exactly on an edge: floating point decides
    want = "exceeds" if ev.exceeds_sesoi else ("equivalent" if ev.equivalent else "undetermined")
    assert th.decision(d) == want


def test_thresholds_worked_example():
    th = evaluate(4.2, 1.6, 58, 0.05, "single", None).thresholds()
    assert th.met_below == pytest.approx(0.99725, abs=1e-5)
    assert th.equivalence_above == pytest.approx(7.40275, abs=1e-5)
    assert [th.decision(x) for x in (0.5, 3, 8)] == ["exceeds", "undetermined", "equivalent"]
    std = evaluate(4.2, 1.6, 58, 0.05, "standard", None).thresholds()
    assert std.equivalence_level == pytest.approx(0.90) and std.met_level == pytest.approx(0.95)
    assert std.equivalence_above < th.equivalence_above
    assert evaluate(0.1, 1.0, None, 0.05, "single", None).thresholds().met_below is None
    with pytest.raises(ValueError):
        th.decision(0)
