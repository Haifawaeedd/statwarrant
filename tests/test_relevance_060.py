"""The test for relevant differences (Hodges & Lehmann, 1954) as the minimal-effect test.

Reference values for the normal case were computed independently in Wolfram Language:
for bounds of half-width 0.5 SE the folded-normal critical value c solving
P(|N(0.5, 1)| > c) = 0.05 is 2.1814774423281538, i.e. q(a) + 0.5.
"""

import math

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant._core import relevance_critical, relevance_tail


def test_relevance_matches_independent_folded_normal_value():
    assert relevance_critical(1.0, 0.05, None) + 0.5 == pytest.approx(2.1814774423281538, rel=1e-12)


@pytest.mark.parametrize("df", [None, 3, 10, 58])
@pytest.mark.parametrize("width", [0.01, 0.2, 1.0, 2.0, 5.0])
def test_largest_type_one_error_is_alpha(width, df):
    dist = stats.norm if df is None else stats.t(df)
    a = relevance_tail(width, 0.05, df)
    q = dist.isf(a)
    # at either bound: the near tail plus the far tail beyond the other bound
    assert a + dist.sf(width + q) == pytest.approx(0.05, rel=1e-10)
    assert 0.025 <= a <= 0.05


def test_limits_of_the_per_side_level():
    assert relevance_tail(0.0, 0.05, None) == 0.025
    assert relevance_tail(math.inf, 0.05, None) == 0.05
    assert relevance_tail(40.0, 0.05, 10) == pytest.approx(0.05, rel=1e-12)
    with pytest.raises(ValueError):
        relevance_tail(-1.0, 0.05, None)


def _plan(method, **kw):
    return sw.declare(sesoi=3, sesoi_source="smallest gain teachers act on", units="points", met_method=method, **kw)


def test_readme_example_under_both_methods():
    split = _plan("split").analyze(estimate=4.2, se=1.6, df=58)
    rel = _plan("relevance").analyze(estimate=4.2, se=1.6, df=58)
    assert split.evidence.p_minimal_effect == pytest.approx(0.2281431728387846, rel=1e-12)
    assert rel.evidence.met_threshold == 0.05
    assert not rel.evidence.exceeds_sesoi
    # the zero test and equivalence test are unchanged by the method
    assert rel.evidence.p_zero == split.evidence.p_zero
    assert rel.evidence.p_equivalence == split.evidence.p_equivalence


def test_relevance_has_more_power_than_split():
    # 90% interval beyond 3, 95% interval not: established only by the relevance test
    est = 3 + 1.75 * 1.6
    split = _plan("split").analyze(estimate=est, se=1.6, df=58)
    rel = _plan("relevance").analyze(estimate=est, se=1.6, df=58)
    assert not split.evidence.exceeds_sesoi
    assert rel.evidence.exceeds_sesoi
    assert rel.evidence.p_minimal_effect < 0.05
    assert rel.evidence.met_interval[0] > 3


def test_minimal_effect_implies_difference_from_zero_and_decisions_agree():
    rng = np.random.default_rng(7)
    for i in range(150):
        se = float(10 ** rng.uniform(-1, 1))
        d = float(se * 10 ** rng.uniform(-1.5, 1))
        est = float(rng.normal(0, 3 * d + 2 * se))
        df = [None, 3, 30][i % 3]
        plan = sw.declare(sesoi=d, sesoi_source="x", met_method="relevance",
                          interval_policy=["single", "standard"][i % 2])
        res = plan.analyze(estimate=est, se=se, df=df)
        ev = res.evidence
        if ev.exceeds_sesoi:
            assert ev.differs_from_zero
            assert ev.p_minimal_effect <= ev.alpha
        expected = "exceeds" if ev.exceeds_sesoi else ("equivalent" if ev.equivalent else "undetermined")
        assert res._declared_position() == expected
        for claim in res.claims.allowed:
            assert res.check(claim.text, record=False).level != "conflict", claim.text


def test_every_threshold_cutoff_is_exact():
    res = _plan("relevance").analyze(estimate=6.5, se=1.6, df=58)
    th = res.thresholds
    d = th.met_below
    assert th.decision(math.nextafter(d, 0)) == "exceeds"
    assert th.decision(d) != "exceeds"
    assert th.to_dict()["met_method"] == "relevance"
    assert th.to_dict()["met_interval_level"] is None
    # wider than under split: the relevance test establishes larger thresholds
    assert d > _plan("split").analyze(estimate=6.5, se=1.6, df=58).thresholds.met_below


def test_fingerprint_unchanged_for_default_and_changed_for_relevance():
    base = sw.declare(sesoi=3, sesoi_source="x")
    assert base.fingerprint == sw.declare(sesoi=3, sesoi_source="x", met_method="split").fingerprint
    assert base.fingerprint != sw.declare(sesoi=3, sesoi_source="x", met_method="relevance").fingerprint
    assert "met_method" not in base.to_dict()


def test_report_names_the_method():
    res = _plan("relevance").analyze(estimate=6.5, se=1.6, df=58)
    md = res.to_markdown()
    assert "relevance (Hodges & Lehmann, 1954)" in md
    assert "relevance test, vs 0.05" in md
    met = res.to_dict()["evidence"]["minimal_effect_test"]
    assert met["method"] == "relevance" and met["p_value_threshold"] == 0.05


def test_unknown_method_is_refused():
    with pytest.raises(ValueError):
        sw.declare(sesoi=3, sesoi_source="x", met_method="other")
