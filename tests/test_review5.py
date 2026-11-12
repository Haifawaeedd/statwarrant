"""Regression tests for 0.4.2: the first-user experiment, its review, and KNOWN_ISSUES.md (0.4.1).

Each test reproduces one example and checks the corrected behaviour.
"""

import math
import warnings

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st
from scipy import stats

import statwarrant as sw
from statwarrant._core import evaluate
from statwarrant.adapters import AdapterMismatch


@pytest.fixture
def std():
    # zero-test p = 0.0111, equivalence-test p = 0.7719
    return sw.declare(sesoi=3, sesoi_source="example", interval_policy="standard").analyze(
        estimate=4.2, se=1.6, df=58)


# ---- 1. p-values and significance bound to the named test ---------------------------

@pytest.mark.parametrize("sentence,level", [
    ("The equivalence test gave p < 0.05.", "conflict"),          # KNOWN_ISSUES 1
    ("The equivalence test gave p > 0.05.", None),
    ("p = 0.77 for the equivalence test.", None),                 # test named after the p-value
    ("Equivalence was not established (TOST p = 0.77).", None),
    ("The equivalence test was not significant (p = 0.77).", None),
    ("The equivalence test was significant.", "conflict"),
    ("The equivalence test was significant (p = 0.011).", "conflict"),
    ("The difference was significant (p = 0.011), but the equivalence test gave p = 0.77.", None),
    ("The difference was significant (p = 0.77).", "conflict"),
    ("The minimal-effect test gave p = 0.77.", "conflict"),
])
def test_named_test_binding(std, sentence, level):
    assert std.check(sentence, record=False).level == level, str(std.check(sentence, record=False))


def test_p_value_naming_two_tests_is_a_check(std):
    res = std.check("The equivalence and minimal-effect tests gave p = 0.77.", record=False)
    assert res.level == "check"


def test_named_test_without_sesoi_is_a_check():
    res = sw.declare().analyze(estimate=4.2, se=1.6, df=58)
    assert res.check("The equivalence test gave p = 0.77.", record=False).level == "check"


# ---- 2. percentage points ---------------------------------------------------------------

@pytest.fixture
def acc():
    return sw.declare(sesoi=0.02, sesoi_source="x", units="accuracy").analyze(
        estimate=0.009259, se=0.008069, df=539)


def test_percentage_points_of_a_proportion(acc):
    s = "The SVM's accuracy advantage was 0.9 percentage points (95% CI -0.7 to 2.5)."
    res = acc.check(s, record=False)
    assert res.status == "no_warnings", str(res)
    assert any("percentage points" in p.reason for p in res.parts)


def test_wrong_percentage_points_still_conflict(acc):
    assert acc.check("The SVM's accuracy advantage was 9 percentage points.", record=False).level == "conflict"
    assert acc.check("The 95% CI was -7 to 25 percentage points.", record=False).level == "conflict"


def test_no_rescaling_when_the_result_is_already_in_points():
    res = sw.declare(units="percentage points").analyze(estimate=0.93, se=0.81, df=539)
    assert res.check("The advantage was 0.9 percentage points.", record=False).status == "no_warnings"


# ---- 3. negation and context ------------------------------------------------------------

def test_did_not_differ_significantly_is_non_significance():
    res = sw.declare(sesoi=15.4, sesoi_source="x", units="units").analyze(estimate=6.65, se=7.37, df=440)
    out = res.check("Disease progression did not differ significantly by sex (p = 0.37).", record=False)
    rules = {p.rule for p in out.parts}
    assert "nonsignificance" in rules and "no-effect" not in rules and "significance" not in rules
    assert out.level == "check"


def test_outcome_noun_is_not_a_direction_claim():
    res = sw.declare(units="log-odds").analyze(estimate=0.0952, se=0.1416)
    out = res.check("TUCE score had no effect on grade improvement.", record=False)
    assert [p.rule for p in out.warnings] == ["no-effect"]
    named = sw.declare(units="points", outcome="score improvement").analyze(estimate=0.3, se=1.0)
    assert "direction" not in [p.rule for p in named.check("We measured score improvement.", record=False).parts]
    # a real direction claim is still read as one
    assert "direction" in [p.rule for p in named.check("Scores showed an improvement.", record=False).warnings]


def test_equivalently_and_plus_minus_bounds():
    res = sw.declare(sesoi=0.02, sesoi_source="x", units="accuracy").analyze(estimate=-0.0037, se=0.0026, df=539)
    out = res.check("The two settings perform practically equivalently within ±0.02 accuracy.", record=False)
    assert out.status == "no_warnings" and "equivalence" in [p.rule for p in out.parts]
    assert res.check("The settings are equivalent within ±0.05.", record=False).level == "conflict"


def test_acronym_in_a_hedge_is_a_name():
    res = sw.declare(sesoi=float(np.log(1.68)), sesoi_source="x", units="log-odds").analyze(estimate=2.3787, se=1.0646)
    s = "Whether the PSI effect reaches the smallest effect size of interest is not determined by these data."
    assert res.check(s, record=False).status == "no_warnings"
    assert res.check("The data are compatible with a positive effect on mood.", record=False).level == "check"


# ---- 4. numerical edge cases from KNOWN_ISSUES.md ---------------------------------------

def test_decision_and_p_value_agree_near_a_threshold():
    base = 1e9
    step = np.spacing(base)
    x = base + np.tile([-1., 1.], 15) * (4 * step)
    d = float(base - 2 * step)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # SciPy may warn about precision loss
        t = stats.ttest_1samp(x, 0)
    ev = sw.declare(sesoi=d, sesoi_source="fixture").analyze(t).evidence
    assert ev.exceeds_sesoi == (ev.p_minimal_effect < ev.met_threshold)
    assert ev.thresholds().decision(d) == ("exceeds" if ev.exceeds_sesoi else "undetermined")


@settings(max_examples=500, deadline=None)
@given(
    est=st.floats(-1e6, 1e6, allow_nan=False),
    se=st.floats(1e-3, 1e3, allow_nan=False),
    gap=st.floats(-5, 5, allow_nan=False),
    policy=st.sampled_from(["single", "standard"]),
)
def test_decisions_always_match_their_p_values(est, se, gap, policy):
    """Bounds placed near the decision boundary: decision and p-value must agree."""
    from statwarrant._core import _dist
    c = float(_dist(None).isf(0.025))
    high = abs(est) + se * (c + gap * 1e-9) + 1e-300
    ev = evaluate(est, se, None, 0.05, policy, (-high, high))
    zero_margin = abs(abs(est) / se - c)
    if zero_margin > 1e-12:
        assert ev.differs_from_zero == (ev.p_zero < 0.05)
    assert ev.exceeds_sesoi == (ev.p_minimal_effect < ev.met_threshold) or \
        math.isclose(ev.p_minimal_effect, ev.met_threshold, rel_tol=1e-9)
    assert ev.equivalent == (ev.p_equivalence < ev.equivalence_threshold) or \
        math.isclose(ev.p_equivalence, ev.equivalence_threshold, rel_tol=1e-9)


def test_large_offset_null_value_is_recorded():
    x = 1e14 + np.array([-.325, -.275, -.175, -.025, .175, .425, .725, -.25, .15, .6])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        t = stats.ttest_1samp(x, 1e14 - 1e5)
    res = sw.declare().analyze(t)
    assert res.null == pytest.approx(1e14 - 1e5, rel=1e-12)
    assert res.evidence.estimate == pytest.approx(1e5, rel=1e-6)


@pytest.mark.parametrize("p", [-1e-300, 1.5, -0.2])
def test_malformed_p_values_are_refused(p):
    class Bad:
        params = np.array([1.0])
        bse = np.array([1.0])
        tvalues = np.array([1.0])
        pvalues = np.array([p])
        use_t = False

    with pytest.raises(AdapterMismatch, match="not a probability"):
        sw.declare().analyze(Bad(), term=0)


def test_tiny_p_values_are_compared_on_the_log_scale():
    z = 35.0  # two-sided normal p about 1e-268
    true_p = 2 * stats.norm.sf(z)

    class Tiny:
        params = np.array([z])
        bse = np.array([1.0])
        tvalues = np.array([z])
        use_t = False

        def __init__(self, p):
            self.pvalues = np.array([p])

    sw.declare().analyze(Tiny(true_p), term=0)  # consistent: accepted
    with pytest.raises(AdapterMismatch):
        sw.declare().analyze(Tiny(1e-300), term=0)


def test_inputs_too_large_for_floating_point_are_refused():
    with pytest.raises(ValueError, match="too large"):
        sw.declare().analyze(estimate=1e308, se=1e308)
    with pytest.raises(ValueError, match="too large"):
        sw.declare(sesoi=1e308, sesoi_source="x").analyze(estimate=-1e308, se=1.0)


# ---- 5. paired comparisons with few differing items -------------------------------------

def test_few_differing_items_get_a_caution():
    res = sw.declare(sesoi=0.02, sesoi_source="x").analyze_paired([1.0] * 538 + [0, 0], [1.0] * 540)
    assert res.raw_input["n_differing_items"] == 2
    assert "Only 2 of 540 items differ" in res.claims.notes[0]
    many = sw.declare().analyze_paired(np.r_[np.ones(30), np.zeros(30)], np.r_[np.zeros(30), np.ones(30)])
    assert not any("items differ" in n for n in many.claims.notes)
