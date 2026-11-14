"""0.5.1: a p-value or 'significant' is tied to the test named nearest before it.

The two cases from the claim-binding review (draft pull request #2) are reproduced
exactly: an independent p-value conflict must survive, and a p-value of a test
statwarrant did not run must not be called consistent.
"""

import pytest

import statwarrant as sw

R = sw.declare(sesoi=2, sesoi_source="example").analyze(estimate=4, se=1)  # p_zero about 0.000063
NS = sw.declare(sesoi=2, sesoi_source="example").analyze(estimate=1, se=1)
PZ = f"{R.evidence.p_zero:.6f}"


def parts(res, sentence):
    return [(p.rule, p.status) for p in res.check(sentence, record=False).parts]


def test_review_case_1_independent_conflict_is_kept():
    out = parts(R, "The one-sided test was significant despite the equivalence test giving p = 0.000063.")
    assert ("p-value", "conflict") in out           # the equivalence test's p is about 0.977
    assert ("significance", "check") in out         # which one-sided test is not said


def test_review_case_2_other_test_is_not_the_zero_test():
    out = parts(R, "The zero test preceded the permutation test, whose p-value was 0.000063.")
    assert out == [("p-value", "check")]


@pytest.mark.parametrize("sentence", [
    "Fisher's exact test was significant (p = 0.01).",
    "The permutation test gave p = 0.03.",
    "The bootstrap analysis was significant.",
    "A sensitivity analysis was significant.",
    "The chi-square test gave p = 0.002.",
    "The effect was significant in the one-sided test.",
])
def test_tests_statwarrant_did_not_run_are_checks(sentence):
    out = parts(NS, sentence)
    assert out and all(status == "check" for _, status in out), out


def test_named_zero_test_is_judged():
    assert parts(R, f"The zero test gave p = {PZ}.") == [("p-value", "consistent")]
    assert parts(R, "The zero test gave p = 0.4.") == [("p-value", "conflict")]


def test_each_p_value_binds_to_its_own_test():
    out = parts(R, "The equivalence test was not significant (p = 0.98), unlike the zero test (p = 0.4).")
    assert out.count(("p-value", "consistent")) == 1 and out.count(("p-value", "conflict")) == 1


def test_two_one_sided_tests_is_still_the_equivalence_test():
    assert ("p-value", "consistent") in parts(R, "The two one-sided tests were not significant (p = 0.98).")


def test_unnamed_significance_is_still_judged():
    assert parts(NS, "The result was significant, as was the bootstrap analysis.")[0] == ("significance", "conflict")
