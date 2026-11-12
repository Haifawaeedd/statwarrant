"""Regression tests for the independent review of the release-0.4.2 branch (KNOWN_ISSUES.md).

Each test reproduces a documented case and checks the corrected behaviour.
"""

import json
import math
import warnings

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st
from scipy import stats

import statwarrant as sw
from statwarrant._core import evaluate


@pytest.fixture
def std():
    # zero-test p = 0.0111, equivalence-test p = 0.7719
    return sw.declare(sesoi=3, sesoi_source="example", interval_policy="standard").analyze(
        estimate=4.2, se=1.6, df=58)


# ---- named tests -------------------------------------------------------------------------

@pytest.mark.parametrize("sentence,level", [
    ("For the equivalence test, p = 0.011.", "check"),          # the documented case
    ("For the equivalence test, p = 0.77.", "check"),
    ("For the equivalence test, the result was significant.", "check"),
    ("The difference was significant (p = 0.011), but the equivalence test gave p = 0.77.", None),
    ("The difference was significant (p = 0.011).", None),
])
def test_test_named_across_a_comma_is_never_silently_consistent(std, sentence, level):
    assert std.check(sentence, record=False).level == level, str(std.check(sentence, record=False))


# ---- percentage points ---------------------------------------------------------------------

@pytest.mark.parametrize("units,estimate,se", [("metres", 0.009, 0.008), ("log-odds", 0.4, 0.2), (None, 0.009, 0.008)])
def test_percentage_points_are_not_converted_for_other_units(units, estimate, se):
    res = sw.declare(units=units).analyze(estimate=estimate, se=se, df=100)
    out = res.check("The difference was 0.9 percentage points.", record=False)
    assert out.level == "check" and "cannot be converted" in out.warnings[0].reason


def test_only_numbers_attached_to_percentage_points_are_rescaled():
    acc = sw.declare(sesoi=0.02, sesoi_source="x", units="accuracy").analyze(estimate=0.009259, se=0.008069, df=539)
    assert acc.check("The advantage was 0.9 percentage points (SE 0.008).", record=False).status == "no_warnings"
    assert acc.check("The advantage was 0.9 percentage points (95% CI -0.7 to 2.5).",
                     record=False).status == "no_warnings"
    # an unattached interval on the percentage-point scale is a check, not a conflict
    out = acc.check("The advantage was 0.9 percentage points; the 95% CI was -0.7 to 2.5.", record=False)
    assert out.level == "check"


# ---- negation scope ------------------------------------------------------------------------

def test_negation_does_not_hide_a_direction_in_another_clause():
    pos = sw.declare(sesoi=0.2, sesoi_source="x").analyze(estimate=0.6, se=0.1)
    out = pos.check("The difference was not significant, and scores decreased.", record=False)
    assert "direction" in [w.rule for w in out.warnings]
    inside = pos.check("Scores did not significantly decrease.", record=False)
    assert "direction" not in [p.rule for p in inside.parts]


@pytest.mark.parametrize("estimate,se,level", [(-0.6, 0.1, "conflict"), (-0.08, 0.03, None), (0.08, 0.03, "conflict")])
def test_combined_size_and_direction_claims(estimate, se, level):
    res = sw.declare(sesoi=0.2, sesoi_source="x").analyze(estimate=estimate, se=se)
    assert res.check("There was a small but significant decrease.", record=False).level == level


def test_size_word_about_something_else_is_not_a_size_claim():
    res = sw.declare(sesoi=0.2, sesoi_source="x").analyze(estimate=0.6, se=0.1)
    out = res.check("The sample was small but the effect was positive.", record=False)
    assert "small" not in [p.rule for p in out.parts]


# ---- printed cut-offs agree with decision() ----------------------------------------------

@settings(max_examples=400, deadline=None)
@given(est=st.floats(-1e6, 1e6, allow_nan=False), se=st.floats(1e-4, 1e4, allow_nan=False),
       df=st.one_of(st.none(), st.floats(2, 500)), policy=st.sampled_from(["single", "standard"]))
def test_cut_offs_are_exactly_where_decision_changes(est, se, df, policy):
    th = evaluate(est, se, df, 0.05, policy, None).thresholds()
    if th.met_below is not None and th.met_below > 0:
        assert th.decision(th.met_below) != "exceeds"
        below = math.nextafter(th.met_below, 0)
        if below > 0:
            assert th.decision(below) == "exceeds"
    assert th.decision(th.equivalence_above) != "equivalent"
    assert th.decision(math.nextafter(th.equivalence_above, math.inf)) == "equivalent"


# ---- adapters ------------------------------------------------------------------------------

def test_unresolvable_small_null_is_disclosed():
    x = 1e14 + np.array([-.325, -.275, -.175, -.025, .175, .425, .725, -.25, .15, .6])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        t = stats.ttest_1samp(x, 0.5)
    res = sw.declare().analyze(t)
    assert res.null == 0.0
    assert any("can only be resolved" in n for n in res.claims.notes)
    assert res.raw_input["provenance_notes"]


@pytest.mark.parametrize("z", [30.0, 34.0, 40.0])
def test_reported_p_of_zero_is_accepted_but_disclosed(z):
    class Zero:
        params = np.array([z])
        bse = np.array([1.0])
        tvalues = np.array([z])
        pvalues = np.array([0.0])
        use_t = False

    res = sw.declare().analyze(Zero(), term=0)
    assert any("reports p = 0" in n for n in res.claims.notes)


def test_tiny_baseline_is_refused():
    with pytest.raises(ValueError, match="relative change overflows"):
        sw.declare().analyze(estimate=1.0, se=0.5, baseline=1e-310)


def test_large_integer_scores_keep_their_differences():
    big = 2 ** 53
    res = sw.declare().analyze_paired([big + 1, big + 3, big + 1, big + 3], [big, big, big, big])
    assert res.evidence.estimate == 2.0
    assert res.raw_input["n_differing_items"] == 4
    json.loads(res.to_json())
