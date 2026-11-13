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
