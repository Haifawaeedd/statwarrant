"""0.5.1: the cases from the review of the 0.5.1 v2 bundle (draft pull request #3)."""

import pytest

import statwarrant as sw

R = sw.declare(sesoi=2, sesoi_source="example").analyze(estimate=4, se=1)  # zero p ~ 0.000063, equivalence p ~ 0.977


def parts(res, sentence):
    return [(p.rule, p.status) for p in res.check(sentence, record=False).parts]


# ---- 1. test binding across clauses -----------------------------------------------------------

def test_significance_binds_to_the_test_after_it_with_a_preposition():
    out = parts(R, "The zero test was significant whereas the result was significant in the equivalence test.")
    assert out == [("significance", "consistent"), ("significance", "conflict")]


def test_opening_phrase_binds_across_the_comma():
    assert parts(R, "For the zero test, p = 0.977250.") == [("p-value", "conflict")]
    assert parts(R, f"For the zero test, p = {R.evidence.p_zero:.6f}.") == [("p-value", "check")]


def test_a_test_named_with_its_null_is_still_that_test():
    assert parts(R, "The permutation test of zero gave p = 0.000063.") == [("p-value", "check")]


# ---- 2. subgroup and causal wording -------------------------------------------------------------

@pytest.fixture
def subgroup_result():
    return sw.declare(subgroup="men with diabetes", design="randomised", outcome="exam score").analyze(estimate=4, se=1)


@pytest.mark.parametrize("sentence", ["The effect was significant in women with diabetes.",
                                      "The effect was significant in men with diabetes."])
def test_subgroup_is_always_verified_by_hand(subgroup_result, sentence):
    out = dict(parts(subgroup_result, sentence))
    assert out["subgroup"] == "check"


@pytest.mark.parametrize("sentence", ["The treatment caused cancer.", "The treatment caused higher exam scores."])
def test_causal_wording_is_never_consistent(subgroup_result, sentence):
    assert dict(parts(subgroup_result, sentence))["causal"] == "check"


def test_causal_wording_with_an_observational_design_is_still_a_conflict():
    r = sw.declare(design="observational").analyze(estimate=4, se=1)
    assert dict(parts(r, "The treatment caused higher scores."))["causal"] == "conflict"


# ---- 3. a claim inside an aside is checked on its own ----------------------------------------------

def test_aside_inside_an_inconclusive_statement_is_checked():
    r = sw.declare(sesoi=3, sesoi_source="test", units="points", outcome="exam scores", better="higher",
                   design="observational").analyze(estimate=1.8, se=1.8)
    out = dict(parts(r, "The data neither show an effect (the treatment caused harm) nor rule out a meaningful one."))
    assert out["inconclusive"] == "consistent" and out["causal"] == "conflict"


def test_claim_after_yet_is_checked():
    r = sw.declare(sesoi=3, sesoi_source="test", units="points").analyze(estimate=1.8, se=1.8)
    out = parts(r, "The data are compatible with no effect and with an effect larger than 3 points yet prove "
                   "the method works.")
    assert ("compatible", "consistent") in out and ("certainty", "conflict") in out
