"""Regression tests for the final review of statwarrant 0.4.0.

Each test reproduces one example from the review and checks the corrected behaviour.
"""

import json

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant.adapters import AdapterMismatch

DIFFS = np.array([-.325, -.275, -.175, -.025, .175, .425, .725, -.25, .15, .6])


# ---- 1. SciPy precision -------------------------------------------------------

def test_large_offset_scipy_agrees_with_direct():
    base = 1e14
    x = base + DIFFS
    plan = sw.declare(sesoi=.3607, sesoi_source="review example")
    adapted = plan.analyze(stats.ttest_1samp(x, base)).evidence
    direct = plan.analyze(estimate=x.mean() - base, se=stats.sem(x), df=9).evidence
    assert adapted.se == pytest.approx(direct.se, rel=1e-9)
    assert adapted.equivalent == direct.equivalent


@pytest.mark.parametrize("offset", [0.0, 1e3, 1e8, 1e12, 1e14])
@pytest.mark.parametrize("scale", [1e-6, 1.0, 1e6])
def test_offset_and_rescaling_never_disagree_silently(offset, scale):
    """Shifted or rescaled data give the direct answer, or are refused; never a different answer."""
    x = (offset + DIFFS) * scale
    null = offset * scale
    plan = sw.declare(sesoi=.3607 * scale, sesoi_source="example")
    direct = plan.analyze(estimate=x.mean() - null, se=stats.sem(x), df=9).evidence
    try:
        adapted = plan.analyze(stats.ttest_1samp(x, null)).evidence
    except (ValueError, AdapterMismatch):
        return
    assert adapted.se == pytest.approx(direct.se, rel=1e-6)
    assert adapted.claim_class == direct.claim_class


def test_ill_conditioned_published_interval_is_refused():
    with pytest.raises(ValueError, match="too narrow"):
        sw.declare().analyze(ci=(1e14 - 0.27, 1e14 + 0.27))


def test_ill_conditioned_scipy_without_stored_se_is_refused():
    class OldStyle:  # a t-test result without SciPy's stored standard error
        def __init__(self, r):
            self.statistic, self.pvalue, self.df = r.statistic, r.pvalue, r.df
            self._r = r

        def confidence_interval(self, confidence_level=0.95):
            return self._r.confidence_interval(confidence_level)

    r = stats.ttest_1samp(1e14 + DIFFS, 1e14)
    with pytest.raises(ValueError, match="too narrow"):
        sw.declare().analyze(OldStyle(r))


# ---- 2. linter ------------------------------------------------------------------

@pytest.fixture
def r():
    return sw.declare(sesoi=3, sesoi_source="teachers", units="points").analyze(estimate=4.2, se=1.6, df=58)


def test_compatible_with_no_positive_effect_warns(r):
    res = r.check("The data are compatible with no positive effect.")
    assert res.level == "conflict"
    assert not any(p.rule == "compatible" and p.status == "consistent" for p in res.parts)


@pytest.mark.parametrize("sentence,rule", [
    ("The data are compatible with a positive effect caused by the drug.", "causal"),
    ("The data are compatible with a positive effect for all students.", "generalization"),
])
def test_compatible_phrase_does_not_swallow_other_claims(r, sentence, rule):
    res = r.check(sentence)
    assert rule in [w.rule for w in res.warnings], str(res)


def test_unassessed_words_in_a_hedge_are_not_consistent(r):
    res = r.check("The data are compatible with a positive effect and the drug is safe.")
    assert "and the drug is safe" in res.unchecked
    res2 = r.check("The data are compatible with a positive effect on mood.")
    hedge = [p for p in res2.parts if p.rule == "compatible"][0]
    assert hedge.status == "check" and "mood" in hedge.reason


def test_p_equals_zero_conflicts(r):
    assert r.check("The p-value was 0.").level == "conflict"
    assert r.check("The p-value was 0.01.").status == "no_warnings"


def test_p_value_is_bound_to_its_test():
    rs = sw.declare(sesoi=3, sesoi_source="t", units="points", interval_policy="standard").analyze(
        estimate=4.2, se=1.6, df=58)
    p_eq = rs.evidence.p_equivalence
    assert rs.check(f"The difference was significant (p = {p_eq:.2g}).").level == "conflict"
    assert rs.check(f"The equivalence test gave p = {p_eq:.2g}.").status == "no_warnings"


def test_stated_level_is_bound_to_the_endpoints():
    rs = sw.declare(sesoi=3, sesoi_source="t", units="points", interval_policy="standard").analyze(
        estimate=4.2, se=1.6, df=58)
    e90 = rs.evidence.equivalence_interval
    z95 = rs.evidence.zero_interval
    assert rs.check(f"The 95% CI was [{e90[0]:.3g}, {e90[1]:.3g}].").level == "conflict"
    assert rs.check(f"The 90% CI was [{e90[0]:.3g}, {e90[1]:.3g}].").status == "no_warnings"
    assert rs.check(f"The 95% CI was [{z95[0]:.3g}, {z95[1]:.3g}].").status == "no_warnings"


# ---- 3. asymmetric bound ----------------------------------------------------------

def test_huge_lower_bound_does_not_hide_an_upper_crossing():
    res = sw.declare(sesoi=(-1e12, 1), sesoi_source="x").analyze(estimate=0, se=0.7)
    assert res.evidence.zero_interval[1] > 1
    assert res.evidence.claim_class == "inconclusive_one_side"
    assert "beyond" in res.claims.allowed[0].text


@pytest.mark.parametrize("low,high", [(-1e12, 1.0), (-1.0, 1e12), (-2.0, 1.959963984540054)])
def test_near_boundary_classes_follow_the_interval(low, high):
    ev = sw.declare(sesoi=(low, high), sesoi_source="x").analyze(estimate=0, se=1).evidence
    lo, hi = ev.zero_interval
    past_low = lo < low - 1e-12 * max(abs(low), 1)
    past_high = hi > high + 1e-12 * max(abs(high), 1)
    want = {(True, True): "inconclusive_both", (False, False): "inconclusive_at_bound"}.get(
        (past_low, past_high), "inconclusive_one_side")
    assert ev.claim_class == want


# ---- other issues ---------------------------------------------------------------------

def test_verifier_compares_a_tiny_p_value_with_an_ordinary_one():
    class Fake:
        params = np.array([1.0])
        bse = np.array([1.0])
        tvalues = np.array([1.0])
        pvalues = np.array([1e-300])
        use_t = False

    with pytest.raises(AdapterMismatch):
        sw.declare().analyze(Fake(), term=0)


def test_threshold_text_has_no_gap_between_rounded_values():
    res = sw.declare(units="points").analyze(estimate=4.2, se=1.6, df=58)
    th = res.thresholds
    text = " ".join(res._threshold_lines())
    assert repr(th.met_below) in text and repr(th.equivalence_above) in text
    assert th.decision(0.99722) == "exceeds"  # between the displayed 0.9972 and the exact cut-off


def test_cluster_count_follows_the_inference():
    res = sw.declare().analyze_paired([1.0, 2, 3, 4], [0.0] * 4, cluster=[1, 1, "1", "1"])
    assert res.raw_input["n_clusters"] == res.evidence.df + 1 == 2


def test_statsmodels_provenance_is_recorded():
    sm = pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(1)
    x = rng.normal(size=50)
    fit = sm.OLS(0.3 * x + rng.normal(size=50), sm.add_constant(x)).fit()
    raw = sw.declare().analyze(fit, term=1).raw_input
    assert raw["reported_statistic"] == pytest.approx(fit.tvalues[1])
    assert raw["reported_p"] == pytest.approx(fit.pvalues[1])


def test_allowed_claims_show_the_real_level():
    res = sw.declare(sesoi=1, sesoi_source="x", alpha=.001).analyze(estimate=0.1, se=0.1)
    assert "99.9% CI" in res.claims.allowed[0].text and "100% CI" not in res.claims.allowed[0].text


def test_non_finite_design_assumptions_are_refused():
    res = sw.declare(sesoi=1, sesoi_source="x").analyze(estimate=0.1, se=0.1)
    with pytest.raises(ValueError, match="finite"):
        res.design([0.5, float("inf")], source="x")
    res.design([0.5, 1.0], source="x")
    json.loads(res.to_json())


def test_report_warns_that_checked_sentences_are_stored():
    res = sw.declare().analyze(estimate=1, se=1)
    res.check("There is no effect.")
    assert "Remove them before sharing" in res.to_markdown()
