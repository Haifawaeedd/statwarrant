"""Ratio claims, interval ends, 'not associated with' and size words after a longer subject.

Rules developed on the second user trial (its sentences are development data) and checked
here with other wording. None of these sentences comes from the third trial's frozen
evaluation set.
"""

import math

import pytest

import statwarrant as sw

PSI = sw.declare(sesoi=math.log(1.68), sesoi_source="trial", units="log-odds").analyze(
    estimate=2.3786876550933544, se=1.0645642544971325)
ML = sw.declare(sesoi=0.02, sesoi_source="trial", units="accuracy").analyze(
    estimate=0.009259259259259259, se=0.008069670111075561, df=539)
DIA = sw.declare(sesoi=15.418600906598218, sesoi_source="trial", units="progression units").analyze(
    estimate=6.645390070921962, se=7.350162171329782, df=440)
EQUIV = sw.declare(sesoi=0.02, sesoi_source="test", units="accuracy").analyze(estimate=0.001, se=0.003, df=500)


def _level(res, sentence):
    return res.check(sentence, record=False).level


def _rules(res, sentence):
    return {p.rule: p.status for p in res.check(sentence, record=False).parts}


# ---- ratios ----------------------------------------------------------------------------------

@pytest.mark.parametrize("sentence,status", [
    ("The odds of improvement tripled.", "check"),                       # inside the ratio interval
    ("The odds of improvement halved.", "conflict"),                     # a factor of 0.5 is ruled out
    ("The odds differed 10.8-fold.", "consistent"),                      # the estimate
])
def test_ratio_claims_on_a_log_scale(sentence, status):
    rules = _rules(PSI, sentence)
    assert rules.get("ratio", rules.get("fold")) == status, rules


def test_ratio_in_an_unbound_comparison_is_sent_for_review():
    # "rose" is a direction the branch cannot tie to the declared contrast, so the ratio is
    # not judged either; the warning says what was not checked.
    out = PSI.check("The odds of improvement rose about 10.8-fold.", record=False)
    fold = next(p for p in out.parts if p.rule == "fold")
    assert fold.status == "check" and "this ratio" in fold.reason


def test_ratio_without_log_scale_or_baseline_is_a_check():
    res = sw.declare(sesoi=1, sesoi_source="x", units="points").analyze(estimate=3.0, se=1.0)
    assert _rules(res, "The risk of failure doubled.").get("ratio") == "check"


def test_ratio_with_a_baseline_uses_the_relative_change():
    res = sw.declare(sesoi=1, sesoi_source="x", units="cases").analyze(estimate=5.0, se=1.0, baseline=5.0)
    assert _rules(res, "The rate of cases doubled.").get("ratio") == "consistent"
    assert _rules(res, "The rate of cases tripled.").get("ratio") == "conflict"  # +200% is outside


def test_ratio_about_another_outcome_is_left_unchecked():
    res = sw.declare(sesoi=1, sesoi_source="x", units="points").analyze(estimate=3.0, se=1.0)
    out = res.check("The method raised scores and halved dropout.", record=False)
    assert "ratio" not in [p.rule for p in out.parts]
    assert any("halved dropout" in u for u in out.unchecked)


def test_times_needs_a_comparison():
    res = sw.declare(sesoi=0.2, sesoi_source="x", units="log-odds").analyze(estimate=0.5, se=0.1)
    out = res.check("Each item was rated 3 times.", record=False)
    assert "fold" not in [p.rule for p in out.parts]


# ---- interval ends: "could be as large as X" -------------------------------------------------

@pytest.mark.parametrize("res,sentence,status", [
    (ML, "The advantage could be as large as 4 percentage points.", "conflict"),   # beyond the interval
    (ML, "The advantage could be as large as 3 percentage points.", "consistent"),  # 2.51 written to 0 decimals
    (ML, "The advantage could be as large as 1 percentage point.", "check"),       # inside, not an end
    (DIA, "The effect could be as large as 21 units.", "consistent"),               # the upper end
    (DIA, "The effect might be as large as 40 units.", "conflict"),
])
def test_plausible_value_is_an_interval_end(res, sentence, status):
    rules = _rules(res, sentence)
    assert rules.get("plausible-value") == status, rules
    assert "big" not in rules


# ---- associations and size words -------------------------------------------------------------

@pytest.mark.parametrize("res,sentence", [
    (DIA, "Sex was not related to disease progression."),
    (DIA, "Sex was not associated with disease progression."),
    (PSI, "PSI was not associated with grade improvement."),
    (DIA, "Body weight was uncorrelated with progression."),
])
def test_not_associated_is_a_claim_of_no_effect(res, sentence):
    assert _rules(res, sentence).get("no-effect") == "conflict"


def test_not_significantly_associated_stays_a_significance_statement():
    rules = _rules(DIA, "Sex was not significantly associated with disease progression.")
    assert "no-effect" not in rules and rules.get("nonsignificance") == "check"


@pytest.mark.parametrize("res,sentence,status", [
    (DIA, "The difference between the sex groups was small.", "conflict"),
    (DIA, "The effect in the treatment group was small.", "conflict"),
    (EQUIV, "The difference between the two models was negligible.", "consistent"),
])
def test_size_word_after_a_longer_subject(res, sentence, status):
    assert _rules(res, sentence).get("small") == status
