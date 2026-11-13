"""Regression tests for the review of the 0.5.0 release candidate (draft pull request #1).

Each of the first four tests reproduces one case from that review exactly; the others
check variants of the same faults.
"""

import math

import pytest

import statwarrant as sw
from statwarrant.plan import _log_scale

INCONCLUSIVE = sw.declare(sesoi=5, sesoi_source="test", units="points", outcome="test score").analyze(
    estimate=1.0, se=2.0, df=60)
SIGNIFICANT = sw.declare(sesoi=0.5, sesoi_source="test", units="points").analyze(estimate=2.0, se=0.85)


def _parts(res, sentence):
    return [(p.rule, p.status, p.text) for p in res.check(sentence, record=False).parts]


# ---- 1. a baseline with a ratio result ----------------------------------------------------

def test_review_case_1_baseline_with_ratio_is_refused():
    with pytest.raises(ValueError, match="already relative"):
        sw.declare(units="log risk ratio").analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True, baseline=0.2)


@pytest.mark.parametrize("units", ["log hazard ratio", "log-odds", "log odds ratio", "logit", "ln(rate ratio)",
                                   "logarithm of the risk ratio"])
def test_baseline_with_log_units_is_refused(units):
    with pytest.raises(ValueError, match="already relative"):
        sw.declare(units=units).analyze(estimate=-0.19, se=0.05, baseline=0.2)


@pytest.mark.parametrize("units", ["points", "mmHg", "blog visits", "logins per day", "kg"])
def test_baseline_with_other_units_still_works(units):
    res = sw.declare(units=units).analyze(estimate=2.0, se=0.5, baseline=40.0)
    assert res.to_dict()["reporting"]["relative_change"] == pytest.approx(0.05)
    assert not _log_scale(units)


def test_ratio_result_reports_the_relative_change_on_the_ratio_scale():
    res = sw.declare(units="log risk ratio").analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)
    note = [n for n in res.raw_input["provenance_notes"] if n.startswith("On the ratio scale")]
    assert len(note) == 1
    assert "-16.5%" in note[0] and "-25.0%" in note[0] and "-7.0%" in note[0]
    assert "On the ratio scale" in str(res)
    assert "-90" not in str(res)


def test_ratio_with_units_that_do_not_say_log_gets_a_note():
    res = sw.declare(units="risk ratio").analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)
    assert any("log ratios" in n for n in res.raw_input["provenance_notes"])
    res = sw.declare(units="log risk ratio").analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)
    assert not any("log ratios" in n for n in res.raw_input["provenance_notes"])


# ---- 2. an estimate further from the midpoint than rounding explains -----------------------

def test_review_case_2_note_does_not_claim_rounding():
    res = sw.declare(units="points").analyze(estimate=4.4, ci=(1.0, 7.4))
    note = res.raw_input["provenance_notes"][0]
    assert "no more than rounding" not in note
    assert "gap exceeds" in note and "assumes a common precision" in note
    assert "4.4" in note and "4.2" in note and "0.2" in note
    assert "check that the estimate and the interval belong together" in note
    info = res.raw_input["estimate_vs_midpoint"]
    assert info["given"] == 4.4 and info["midpoint"] == pytest.approx(4.2)
    assert info["explained_by_rounding"] is None
    assert info["within_assumed_rounding_allowance"] is False
    assert res.evidence.estimate == pytest.approx(4.2)


@pytest.mark.parametrize("estimate", [4.2, 4.3])
def test_estimate_within_assumed_allowance_gets_a_caveated_note(estimate):
    res = sw.declare(units="points").analyze(estimate=estimate, ci=(1.0, 7.4))
    notes = res.raw_input.get("provenance_notes", [])
    if estimate == 4.2:
        assert notes == [] and "estimate_vs_midpoint" not in res.raw_input
    else:
        assert "gap is within" in notes[0] and "actually explains the difference is unknown" in notes[0]
        assert res.raw_input["estimate_vs_midpoint"]["explained_by_rounding"] is None
        assert res.raw_input["estimate_vs_midpoint"]["within_assumed_rounding_allowance"] is True


def test_estimate_far_from_the_midpoint_is_still_refused():
    with pytest.raises(ValueError, match="not symmetric"):
        sw.declare(units="points").analyze(estimate=4.6, ci=(1.0, 7.4))


def test_given_estimate_is_not_called_a_conflict():
    res = sw.declare(sesoi=2, sesoi_source="test", units="points").analyze(estimate=4.4, ci=(1.0, 7.4))
    out = res.check("The mean difference was 4.4 points (95% CI 1.0 to 7.4).", record=False)
    assert out.level != "conflict"


# ---- 3. a difference between p-values ------------------------------------------------------

def test_review_case_3_difference_in_p_values_is_not_a_p_value():
    parts = _parts(SIGNIFICANT, "The difference in p-values was 0.0111.")
    assert ("p-difference", "check", "difference in p-values was 0.0111") in parts
    assert not any(rule == "p-value" for rule, _, _ in parts)


@pytest.mark.parametrize("sentence", [
    "The difference between the two p-values was 0.0186.",
    "The difference between the p-values was small.",
    "The change in p-value was 0.02.",
    "The p-values differed between the two groups.",
    "The gap between their p values is 0.3.",
    "p dropped from 0.04 to 0.01.",
    "The p-value fell from 0.04 to 0.0186.",
    "The p-value increased after adjustment.",
])
def test_p_value_comparisons_are_checks(sentence):
    parts = _parts(SIGNIFICANT, sentence)
    assert any(rule == "p-difference" and status == "check" for rule, status, _ in parts)
    assert not any(status == "consistent" for _, status, _ in parts)


def test_a_plain_p_value_is_still_checked():
    p = SIGNIFICANT.evidence.p_zero
    assert _parts(SIGNIFICANT, f"p was {p:.3f}.") == [("p-value", "consistent", f"p was {p:.3f}")]
    assert _parts(SIGNIFICANT, "p was 0.0111.")[0][:2] == ("p-value", "conflict")


# ---- 4. claims after a compound negation ---------------------------------------------------

def test_review_case_4_claims_after_the_negation_are_checked():
    s = ("The data support neither equivalence nor an effect larger than the sesoi and prove the treatment "
         "caused harm for everyone.")
    out = INCONCLUSIVE.check(s, record=False)
    parts = {p.rule: p for p in out.parts}
    assert parts["neither-equivalence"].text == "neither equivalence nor an effect larger than the sesoi"
    assert parts["certainty"].status == "conflict"
    assert parts["generalization"].status == "conflict"
    assert "causal" in parts
    assert out.level == "conflict"


@pytest.mark.parametrize("tail, rules", [
    (", which proves the drug works in all patients.", {"certainty", "generalization"}),
    (" because the treatment caused improvement.", {"causal"}),
    ("; the treatment caused improvement.", {"causal"}),
    (" but proves the effect for everyone.", {"certainty", "generalization"}),
])
def test_compound_negation_variants(tail, rules):
    s = "The data support neither equivalence within ±5 points nor an effect larger than 5 points" + tail
    parts = {p.rule for p in INCONCLUSIVE.check(s, record=False).parts}
    assert "neither-equivalence" in parts
    assert rules <= parts


def test_size_qualifier_stays_with_the_negation():
    out = INCONCLUSIVE.check("Neither equivalence nor an effect greater than 5 points was shown.", record=False)
    parts = {p.rule: p for p in out.parts}
    assert parts["neither-equivalence"].text == "Neither equivalence nor an effect greater than 5 points"
    assert out.level == "check"
