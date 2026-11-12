"""A frozen corpus of sentences and the warnings statwarrant should give.

The expected outcomes were written by the maintainers, not by independent
annotators; they guard against regressions, they are not an accuracy estimate.
Columns are scenarios S1-S6 from test_scenarios.py, SESOI 0.2, policy "single".
A = no warnings, N = a "check" warning (no conflict), B = a "conflict" warning.
"""

import pytest

import statwarrant as sw
from statwarrant._core import evaluate
from statwarrant.claims import Context, check_sentence

SCENARIOS = [(0.60, 0.10), (0.30, 0.10), (0.08, 0.03), (0.02, 0.05), (0.15, 0.20), (-0.50, 0.10)]
CODE = {"A": None, "N": "check", "B": "conflict"}

CORPUS = {
    "There was no meaningful effect.": "BBAABB",
    "The program had no real effect on scores.": "BBBBBB",
    "Scores were not lower with the program.": "NNNBBB",
    "The program neither helped nor harmed.": "BBBBBB",
    "The effect was small.": "BBAABB",
    "Scores were slightly higher.": "BBABBB",
    "There was a slight decrease.": "BBBBBB",
    "There is strong evidence of an effect.": "NNNBBN",
    "There is evidence that the program works.": "AAABBB",
    "There is weak evidence of an effect.": "NNNNNN",
    "The effect was marginally significant.": "NNNBBN",
    "The program caused higher scores.": "NNNBBB",
    "The effect is negligible.": "BBAABB",
    "The effect is not different from zero.": "BBBBBB",
    "Nobody benefited from the program.": "BBBBBB",
    "The program did not significantly improve scores.": "BBBNNN",
    "There was no significant difference between groups.": "BBBNNB",
    "The effect is clinically meaningful.": "ABBBBA",
    "An effect of zero cannot be ruled out.": "BBBAAB",
    "The two methods are equivalent (p = 0.02).": "BBBBBB",
    "On average, scores rose by 0.6 (95% CI 0.4 to 0.8).": "ABBBBB",
    "In 2024, the program raised scores.": "NNNBBB",
    "There was no increase in scores.": "BBBBBN",
    "The effect is negative and statistically significant.": "BBBBBA",
    "Scores increased for every student.": "BBBBBB",
    "The program had a huge effect.": "NBBBBN",
}


@pytest.mark.parametrize("sentence", CORPUS)
def test_corpus(sentence):
    got = []
    for est, se in SCENARIOS:
        got.append(check_sentence(sentence, Context(evaluate(est, se, None, 0.05, "single", (-0.2, 0.2)))).level)
    want = [CODE[c] for c in CORPUS[sentence]]
    assert got == want, sentence


def test_nothing_recognised_is_unrecognized():
    ctx = Context(evaluate(0.6, 0.1, None, 0.05, "single", (-0.2, 0.2)))
    assert check_sentence("We used a mixed design.", ctx).status == "no_supported_pattern"


def test_warnings_carry_exact_spans_rules_and_actions():
    ctx = Context(evaluate(4.2, 1.6, 58, 0.05, "single", (-3, 3)), units="points")
    sentence = "The new method improved scores by 100 points."
    res = check_sentence(sentence, ctx)
    assert res.level == "conflict" and res.status == "warnings"
    w = [p for p in res.warnings if p.status == "conflict"][0]
    assert w.rule == "magnitude" and w.text == "by 100" and [sentence[a:b] for a, b in w.spans] == ["by 100"]
    assert w.action
    d = res.to_dict()
    assert d["warnings"][0]["rule"] == "magnitude" and "verdict" not in d
    assert "not proof that the sentence is false" in str(res)


def test_spans_survive_case_and_unicode():
    ctx = Context(evaluate(4.2, 1.6, 58, 0.05, "single", (-3, 3)), units="points")
    sentence = "There Was NO Increase \u2014 scores \u2264 baseline."
    res = check_sentence(sentence, ctx)
    w = res.warnings[0]
    assert w.text == "NO Increase" and [sentence[a:b] for a, b in w.spans] == ["NO Increase"]


def test_no_warnings_is_never_a_clearance():
    ctx = Context(evaluate(4.2, 1.6, 58, 0.05, "single", (-3, 3)), units="points")
    res = check_sentence("Scores increased and the treatment is safe.", ctx)
    assert res.status == "no_warnings" and res.level is None
    assert "and the treatment is safe" in res.unchecked
    assert "not a clearance" in str(res)
    assert not hasattr(res, "verdict")


def _res(kind):
    if kind == "sesoi":
        return sw.declare(sesoi=3, sesoi_source="t", units="points").analyze(estimate=4.2, se=1.6, df=58)
    if kind == "none":
        return sw.declare(units="points").analyze(estimate=4.2, se=1.6, df=58)
    return sw.declare(sesoi=3, sesoi_source="t", units="points",
                      interval_policy="standard").analyze(estimate=0.3, se=0.9, df=58)


# estimate 4.2, SE 1.6, df 58: 95% CI [0.997, 7.4], p = 0.011, positive, importance undetermined
NUMBERS_AND_HEDGES = [
    ("sesoi", "The difference was significant at the 5% level.", "allowed"),
    ("sesoi", "The difference was significant at alpha = 0.01.", "needs_care"),
    ("sesoi", "The 90% CI excluded zero.", "needs_care"),
    ("standard", "The 90% CI lies inside the bounds, so the methods are equivalent.", "allowed"),
    ("sesoi", "The effect was significant (p > 0.05).", "blocked"),
    ("sesoi", "The effect was significant (p < 0.05).", "allowed"),
    ("sesoi", "Scores improved by up to 10 points.", "allowed"),
    ("sesoi", "Scores improved by less than 5 points.", "blocked"),
    ("sesoi", "Scores improved by at least 1 point.", "blocked"),  # the lower end is 0.997
    ("sesoi", "Scores improved by more than 0.5 points.", "allowed"),
    ("sesoi", "Scores fell by 4.2 points.", "blocked"),
    ("sesoi", "Scores changed by 5 points.", "needs_care"),
    ("sesoi", "The program gave a 5-point improvement.", "needs_care"),
    ("none", "Its importance cannot be judged without a smallest effect size of interest.", "allowed"),
    ("sesoi", "Its importance cannot be judged without a smallest effect size of interest.", "blocked"),
    ("sesoi", "This cannot be determined.", "needs_care"),
    ("sesoi", "The answer is not established.", "needs_care"),
    ("sesoi", "Large effects are not ruled out.", "allowed"),
    ("sesoi", "Something is not ruled out.", "needs_care"),
    ("standard", "Equivalence is not established.", "blocked"),
    ("sesoi", "The direction is not established.", "blocked"),
    ("sesoi", "The result is inconclusive.", "blocked"),
    ("sesoi", "The data are compatible with an effect of zero.", "blocked"),
    ("sesoi", "The data are compatible with effects from 1.0 to 7.4 points.", "allowed"),
    ("sesoi", "Positive results were found.", "needs_care"),
    ("sesoi", "The effect is detectable.", "allowed"),
    ("sesoi", "Scores rose from 60 to 64.2 points.", "needs_care"),  # no baseline declared: 60 is unverified
]


OUTCOME = {"allowed": None, "needs_care": "check", "blocked": "conflict"}


@pytest.mark.parametrize("kind,sentence,expected", NUMBERS_AND_HEDGES)
def test_numbers_and_hedges(kind, sentence, expected):
    res = _res(kind).check(sentence)
    assert res.level == OUTCOME[expected], str(res)


# Reported against 0.2.0 by a second review: these got a sentence-level "allowed".
@pytest.mark.parametrize("sentence,rule", [
    ("A 95% credible interval was 1.0 to 7.4.", "interval-level"),
    ("Scores increased in the control group.", "subgroup"),
    ("Scores increased, but only for boys.", "subgroup"),
    ("There is a 95% probability that the true effect lies between 1.0 and 7.4 points.", "probability-misreading"),
    ("The difference is unlikely to be due to chance.", "probability-misreading"),
    ("The posterior mean was 4.2 points.", "bayesian-wording"),
])
def test_second_review_sentences_warn(sentence, rule):
    res = _res("sesoi").check(sentence)
    assert rule in [p.rule for p in res.warnings], str(res)


@pytest.mark.parametrize("sentence,unchecked", [
    ("Scores increased and the treatment is safe.", "and the treatment is safe"),
    ("Scores increased, so the method should be adopted nationwide.", "so the method should be adopted nationwide"),
    ("The new method raised scores by about 4 points and halved dropout.", "halved dropout"),
])
def test_unchecked_text_is_reported(sentence, unchecked):
    res = _res("sesoi").check(sentence)
    assert res.status == "no_warnings" and any(unchecked in u for u in res.unchecked), str(res)
