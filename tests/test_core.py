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


@pytest.mark.parametrize("policy,threshold", [("standard", 0.05), ("single", 0.025)])
@pytest.mark.parametrize("seed", range(30))
def test_decisions_equal_pvalue_rules(policy, threshold, seed):
    rng = np.random.default_rng(200 + seed)
    est, se = rng.normal(0, 0.5), rng.uniform(0.05, 0.5)
    low, high = -rng.uniform(0.05, 1), rng.uniform(0.05, 1)
    ev = evaluate(est, se, None, 0.05, policy, (low, high))
    assert ev.bounds_threshold == threshold
    assert ev.equivalent == (ev.p_equivalence < threshold)
    assert ev.exceeds_sesoi == (ev.p_minimal_effect < threshold)
    assert ev.differs_from_zero == (ev.p_zero < 0.05)


def test_single_policy_uses_one_interval():
    ev = evaluate(0.3, 0.1, None, 0.05, "single", (-0.2, 0.2))
    assert ev.bounds_interval == pytest.approx(ev.zero_interval)
    assert ev.bounds_level == pytest.approx(0.95)


def test_t_distribution_is_used_when_df_given():
    ev_t = evaluate(1.0, 0.5, 5, 0.05, "single", None)
    ev_z = evaluate(1.0, 0.5, None, 0.05, "single", None)
    assert ev_t.zero_interval[1] - ev_t.zero_interval[0] > ev_z.zero_interval[1] - ev_z.zero_interval[0]


@pytest.mark.parametrize("kwargs", [
    dict(estimate=float("nan"), se=1.0),
    dict(estimate=1.0, se=0.0),
    dict(estimate=1.0, se=-1.0),
])
def test_bad_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        evaluate(kwargs["estimate"], kwargs["se"], None, 0.05, "single", None)


def test_declare_validation():
    with pytest.raises(ValueError, match="reason"):
        sw.declare(sesoi=0.2)
    with pytest.raises(ValueError):
        sw.declare(sesoi=(0.1, 0.3), sesoi_source="x")
    with pytest.raises(ValueError):
        sw.declare(sesoi=-1, sesoi_source="x")
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
