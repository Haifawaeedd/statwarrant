"""Regression tests for the independent review of the 0.5.0.dev0 integration branch.

Each test reproduces a counterexample recorded in KNOWN_ISSUES.md (commit d8b94b5) and
checks the corrected behaviour.
"""

import pytest

import statwarrant as sw

INCONCLUSIVE = sw.declare(sesoi=5, sesoi_source="test", units="points", outcome="test score").analyze(
    estimate=1.0, se=2.0, df=60)
LOG_ODDS = sw.declare(sesoi=0.2, sesoi_source="test", units="log-odds", contrast="treatment minus control").analyze(
    estimate=0.69, se=0.1)
NEGATIVE = sw.declare(sesoi=0.5, sesoi_source="test", units="points").analyze(estimate=-2.0, se=0.1)
POSITIVE = sw.declare(sesoi=0.5, sesoi_source="test", units="points").analyze(estimate=2.0, se=0.1)


def _parts(res, sentence):
    return {p.rule: p for p in res.check(sentence, record=False).parts}


# ---- coordinated negation must not hide other claims ------------------------------------

def test_claims_after_neither_nor_are_still_checked():
    s = "The data support neither a difference nor equivalence and prove the treatment caused harm for everyone."
    out = INCONCLUSIVE.check(s, record=False)
    parts = {p.rule: p for p in out.parts}
    assert "prove" not in parts["neither-established"].text
    assert {"certainty", "causal", "generalization"} <= set(parts)
    assert out.level == "conflict"


def test_item_naming_another_outcome_is_a_check():
    parts = _parts(INCONCLUSIVE, "Neither a difference in mortality nor equivalence was established.")
    assert parts["neither-established"].status == "check"
    assert "mortality" in parts["neither-established"].reason


def test_item_with_its_own_margin_is_a_check():
    parts = _parts(INCONCLUSIVE, "Neither a difference from zero nor equivalence within ±20 points was established.")
    assert parts["neither-established"].status == "check"


def test_item_naming_the_declared_outcome_is_judged():
    parts = _parts(INCONCLUSIVE, "Neither a difference in test score nor equivalence was established.")
    assert parts["neither-established"].status == "consistent"


# ---- ratios: quantity, order, negation, no exceptions -----------------------------------

def test_risk_is_not_read_as_odds():
    p = _parts(LOG_ODDS, "The risk doubled.")["ratio"]
    assert p.status == "check" and "ratios differ" in p.reason


@pytest.mark.parametrize("sentence", [
    "Treatment doubled the odds compared with control.",
    "Control doubled the odds compared with treatment.",   # reverse order
])
def test_ratio_order_is_never_marked_consistent(sentence):
    assert _parts(LOG_ODDS, sentence)["ratio"].status == "check"


def test_fold_about_another_quantity_is_not_compared():
    p = _parts(LOG_ODDS, "Hospital admissions differed 2-fold.")["fold"]
    assert p.status == "check" and "does not name the quantity" in p.reason
    # with a direction word the comparison is unbound and the factor is not judged either
    assert _parts(LOG_ODDS, "Hospital admissions rose 2-fold.")["fold"].status == "check"


@pytest.mark.parametrize("sentence", ["The odds were two fold.", "The odds were two-fold.", "The odds were twofold.",
                                      "The odds rose two times as fast.", "The odds were cut in half."])
def test_ratio_wording_never_raises(sentence):
    LOG_ODDS.check(sentence, record=False)


def test_negated_ratio_is_not_judged():
    p = _parts(LOG_ODDS, "Treatment did not double the odds.")["ratio"]
    assert p.status == "check" and "negated" in p.reason


# ---- interval ends: sign and side --------------------------------------------------------

@pytest.mark.parametrize("res,sentence,status", [
    (NEGATIVE, "The effect could be as high as 2.2.", "conflict"),     # the interval is entirely negative
    (NEGATIVE, "The effect could be as low as -2.2.", "consistent"),   # the lower end
    (NEGATIVE, "The effect could be as low as -1.8.", "check"),        # that is the upper end
    (POSITIVE, "The effect could be as low as 2.2.", "check"),         # that is the upper end
    (POSITIVE, "The effect could be as high as 2.2.", "consistent"),
    (NEGATIVE, "The effect could be as large as 2.2.", "check"),       # right size, sign not stated
    (POSITIVE, "The effect could be as small as 1.8.", "consistent"),  # the end nearest zero
    (POSITIVE, "The effect could be as small as 1.0.", "conflict"),    # ruled out
    (INCONCLUSIVE, "The effect could be as small as 1.0.", "check"),   # interval includes zero
])
def test_interval_end_claims(res, sentence, status):
    assert _parts(res, sentence)["plausible-value"].status == status, str(res.check(sentence, record=False))
