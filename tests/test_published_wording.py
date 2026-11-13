"""Options and fixes prompted by checking sentences from published papers (0.5.0).

The sentences here are variants written for the tests, not the frozen published excerpts.
"""

import math

import pytest

import statwarrant as sw


def _parts(res, sentence):
    return {p.rule: p for p in res.check(sentence, record=False).parts}


# ---- design --------------------------------------------------------------------------------

def test_causal_wording_with_a_randomised_design_and_an_established_effect():
    res = sw.declare(design="randomised", units="points").analyze(estimate=4.0, se=1.0)
    assert _parts(res, "The program led to higher scores.")["causal"].status == "consistent"


def test_causal_wording_with_a_randomised_design_but_no_established_effect():
    res = sw.declare(design="randomized", units="points").analyze(estimate=1.0, se=1.0)
    assert res.plan.design == "randomised"
    assert _parts(res, "The program led to higher scores.")["causal"].status == "check"


def test_causal_wording_with_an_observational_design_is_a_conflict():
    res = sw.declare(design="observational", units="points").analyze(estimate=4.0, se=1.0)
    assert _parts(res, "Drinking coffee caused lower mortality.")["causal"].status == "conflict"


def test_unknown_design_is_refused_and_undeclared_design_still_asks():
    with pytest.raises(ValueError, match="design"):
        sw.declare(design="quasi")
    res = sw.declare(units="points").analyze(estimate=4.0, se=1.0)
    assert _parts(res, "The program led to higher scores.")["causal"].status == "check"


def test_design_and_subgroup_change_the_fingerprint_only_when_given():
    base = sw.declare(units="points")
    assert sw.declare(units="points", design=None).fingerprint == base.fingerprint
    assert sw.declare(units="points", design="randomised").fingerprint != base.fingerprint
    assert sw.declare(units="points", subgroup="girls").fingerprint != base.fingerprint


# ---- cautions about proof and causation ------------------------------------------------

@pytest.mark.parametrize("sentence", [
    "This study does not prove that the program raises scores.",
    "The data cannot prove cause and effect.",
    "These results don't imply causation.",
])
def test_cautions_are_not_conflicts(sentence):
    res = sw.declare(design="observational", units="points").analyze(estimate=4.0, se=1.0)
    out = res.check(sentence, record=False)
    assert out.level != "conflict", str(out)
    assert "unattached-negation" not in [p.rule for p in out.parts]


def test_affirmed_proof_is_still_a_conflict():
    res = sw.declare(units="points").analyze(estimate=4.0, se=1.0)
    assert _parts(res, "This study proves that the program works.")["certainty"].status == "conflict"


# ---- subgroup results ------------------------------------------------------------------------

def test_sentence_naming_the_declared_subgroup():
    res = sw.declare(subgroup="patients receiving no respiratory support", units="log rate ratio").analyze(
        ci=(-0.09, 0.44))
    s = "Among patients who were not receiving respiratory support, no benefit was evident."
    assert _parts(res, s)["subgroup"].status == "consistent"


@pytest.mark.parametrize("sentence", [
    "Among patients who were on invasive mechanical ventilation, mortality was lower.",  # another subgroup
    "Among patients who were receiving respiratory support, mortality was lower.",  # negation differs
])
def test_sentence_naming_another_subgroup_is_a_check(sentence):
    res = sw.declare(subgroup="patients receiving no respiratory support", units="log rate ratio").analyze(
        ci=(-0.09, 0.44))
    assert _parts(res, sentence)["subgroup"].status == "check"


# ---- counts and time points are not effects ------------------------------------------------

@pytest.mark.parametrize("sentence,count", [
    ("Mortality at 90 days was lower with the drug.", "90"),
    ("The 30-day readmission rate was lower with the drug.", "30"),
    ("Events occurred in 512 participants (18.4%) in the drug group.", "18.4"),
])
def test_counts_and_time_points_are_not_read_as_effects(sentence, count):
    res = sw.declare(units="log risk ratio").analyze(ci=(-0.4, -0.1))
    out = res.check(sentence, record=False)
    assert all(count not in p.text for p in out.parts), str(out)


def test_time_in_the_declared_unit_is_still_read():
    res = sw.declare(units="days").analyze(estimate=2.0, se=0.5)
    assert any("9" in p.text for p in res.check("The stay was shorter by 9 days.", record=False).parts)


# ---- published ratios with rounded intervals -------------------------------------------

def test_published_ratio_with_rounded_interval_is_accepted():
    with pytest.raises(ValueError, match="not symmetric"):
        sw.declare().analyze(estimate=math.log(0.83), ci=(math.log(0.75), math.log(0.93)))
    res = sw.declare(units="log rate ratio").analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)
    assert res.raw_input["ratio_scale_input"] is True and "ratio scale" in res.source
    lo, hi = res.evidence.zero_interval
    assert math.exp(lo) == pytest.approx(0.75) and math.exp(hi) == pytest.approx(0.93)


def test_ratio_input_still_refuses_a_truly_asymmetric_interval():
    with pytest.raises(ValueError, match="not symmetric"):
        sw.declare().analyze(estimate=0.60, ci=(0.75, 0.93), ratio=True)


@pytest.mark.parametrize("ci", [(0.0, 1.2), (-0.5, 1.2)])
def test_ratio_input_must_be_positive(ci):
    with pytest.raises(ValueError, match="positive"):
        sw.declare().analyze(ci=ci, ratio=True)


# ---- words that name outcomes or study size --------------------------------------------

@pytest.mark.parametrize("sentence", [
    "Coffee consumption was inversely associated with total and cause-specific mortality.",
    "All-cause mortality was lower among coffee drinkers.",
])
def test_cause_in_an_outcome_name_is_not_causal_wording(sentence):
    res = sw.declare(design="observational", units="log hazard ratio").analyze(estimate=0.90, ci=(0.85, 0.96), ratio=True)
    assert "causal" not in [p.rule for p in res.check(sentence, record=False).parts]


def test_size_of_the_study_is_not_a_size_claim():
    res = sw.declare(units="log hazard ratio").analyze(estimate=0.90, ci=(0.85, 0.96), ratio=True)
    assert "big" not in [p.rule for p in res.check("In this large prospective study, mortality was lower.",
                                                   record=False).parts]
    assert "big" in [p.rule for p in res.check("The study found a large effect.", record=False).parts]


# ---- adversarial review of the new options ---------------------------------------------

@pytest.mark.parametrize("estimate,accepted", [(4.2, True), (4.4, True), (4.5, False), (4.6, False)])
def test_rounding_allowance_uses_the_common_printed_precision(estimate, accepted):
    # 1.0 is printed to one decimal like 4.2 and 7.4, so it must not widen the allowance.
    plan = sw.declare()
    if accepted:
        plan.analyze(estimate=estimate, ci=(1.0, 7.4))
    else:
        with pytest.raises(ValueError, match="not symmetric"):
            plan.analyze(estimate=estimate, ci=(1.0, 7.4))


def test_estimate_differing_from_the_midpoint_by_rounding_is_disclosed():
    res = sw.declare(units="log rate ratio").analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)
    assert any("differs from the interval's midpoint" in n and "0.83" in n for n in res.claims.notes)
    exact = sw.declare().analyze(estimate=4.2, ci=(1.0, 7.4))
    assert not any("midpoint" in n for n in exact.claims.notes)


@pytest.mark.parametrize("kwargs", [dict(estimate=0.8, ratio=True), dict(estimate=0.8, se=0.1, ratio=True),
                                    dict(ci=(0.9, 0.9), ratio=True)])
def test_ratio_input_errors(kwargs):
    with pytest.raises(ValueError):
        sw.declare().analyze(**kwargs)


@pytest.mark.parametrize("alias,design", [("RCT", "randomised"), ("Randomized controlled trial", "randomised"),
                                          ("cohort", "observational"), ("case-control", "observational"),
                                          ("cross_sectional", "observational")])
def test_design_aliases(alias, design):
    assert sw.declare(design=alias).design == design


@pytest.mark.parametrize("sentence,number", [
    ("Sleep improved by 2 hours over 12 weeks.", "12"),
    ("After 12 weeks sleep improved by 2 hours.", "12"),
])
def test_time_points_in_another_unit_than_the_effect_are_skipped(sentence, number):
    res = sw.declare(units="hours", sesoi=1, sesoi_source="x").analyze(estimate=2.0, se=0.5)
    out = res.check(sentence, record=False)
    assert all(p.text != number for p in out.parts), str(out)
    assert any(p.rule == "magnitude" for p in out.parts)


@pytest.mark.parametrize("sentence", ["Stay was shorter by 2 days.", "A difference of 2 days was found."])
def test_effects_stated_in_time_units_are_still_read(sentence):
    res = sw.declare(units="hours").analyze(estimate=2.0, se=0.5)
    assert any("2" in p.text for p in res.check(sentence, record=False).parts)


def test_caution_and_claim_in_one_sentence_are_judged_separately():
    res = sw.declare(design="observational").analyze(estimate=1.0, se=0.3)
    rules = {p.rule: p.status for p in res.check("This cannot prove harm; coffee caused the decline.",
                                                 record=False).parts}
    assert rules["caution"] == "consistent" and rules["causal"] == "conflict"
    rules = {p.rule: p.status for p in res.check("The results prove the effect but do not imply causation.",
                                                 record=False).parts}
    assert rules["certainty"] == "conflict" and rules["caution"] == "consistent"


from hypothesis import given, settings, strategies as st  # noqa: E402


@settings(max_examples=300, deadline=None)
@given(log_est=st.floats(-3, 3), se=st.floats(0.01, 1.0), decimals=st.sampled_from([2, 3]))
def test_rounded_published_ratios_are_always_accepted(log_est, se, decimals):
    est, lo, hi = (round(math.exp(x), decimals) for x in (log_est, log_est - 1.959964 * se, log_est + 1.959964 * se))
    if lo <= 0 or hi <= lo or est <= 0:
        return
    res = sw.declare().analyze(estimate=est, ci=(lo, hi), ratio=True)
    same = sw.declare().analyze(ci=(math.log(lo), math.log(hi)))
    assert res.evidence.estimate == pytest.approx(same.evidence.estimate)
    assert (res.evidence.differs_from_zero, res.evidence.direction) == (same.evidence.differs_from_zero,
                                                                        same.evidence.direction)
