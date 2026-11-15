"""0.5.1: a claim of significance when the zero test is not significant.

In 0.5.0 the quick start's own sentence, "The new method significantly improved
scores.", got only "to verify" for a non-significant result (p = 0.258), because the
significance word sat inside a comparison that could not be tied to the declared
contrast. Declaring the contrast, or passing a SciPy result, weakened the warning
that estimate + SE without a contrast gave. When the zero test is not significant,
significance is ruled out in both orders, so the comparison's order does not matter.
"""

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw


CONTRAST = dict(outcome="exam score", contrast="new method minus existing method")
BASE = dict(sesoi=3, sesoi_source="smallest score gain teachers act on", units="points",
            scope="first-year students, one university, one term")


def _groups():
    rng = np.random.default_rng(7)  # the quick start's data: p = 0.258
    return rng.normal(64, 6, 30), rng.normal(60, 6, 30)


def _result(route, estimate, se):
    if route == "estimate-se":
        return sw.declare(**BASE).analyze(estimate=estimate, se=se, df=58)
    if route == "estimate-se, contrast":
        return sw.declare(**BASE, **CONTRAST).analyze(estimate=estimate, se=se, df=58)
    if route == "no sesoi, contrast":
        return sw.declare(units="points", **CONTRAST).analyze(estimate=estimate, se=se, df=58)
    new, old = _groups()
    if route == "scipy":
        return sw.declare(**BASE).analyze(stats.ttest_ind(new, old))
    if route == "scipy, contrast":
        return sw.declare(**BASE, **CONTRAST).analyze(stats.ttest_ind(new, old))
    raise ValueError(route)


ROUTES = ["estimate-se", "estimate-se, contrast", "no sesoi, contrast", "scipy", "scipy, contrast"]

CLAIMS_OF_SIGNIFICANCE = [
    "The new method significantly improved scores.",
    "The new method significantly lowered scores.",
    "Scores were significantly different between the groups.",
    "Students taught with the new method scored significantly higher than those taught with the "
    "existing method.",
]


def _significance_parts(out):
    return [p for p in out.parts if p.rule == "significance"]


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("sentence", CLAIMS_OF_SIGNIFICANCE)
def test_significance_claim_conflicts_in_either_order(route, sentence):
    res = _result(route, 1.54, 1.35)
    assert not res.evidence.differs_from_zero
    out = res.check(sentence, record=False)
    assert out.level == "conflict", str(out)
    parts = _significance_parts(out)
    assert parts and all(p.status == "conflict" for p in parts), str(out)
    assert "not statistically significant" in parts[0].reason


@pytest.mark.parametrize("route", ["estimate-se, contrast", "no sesoi, contrast"])
def test_significant_result_still_needs_the_order(route):
    # With a significant result the direction decides, and an unbound comparison
    # cannot be judged: the significance part stays "to verify", not a conflict.
    res = _result(route, 4.2, 1.6)
    for sentence in ("The new method significantly improved scores.",
                     "The new method significantly lowered scores."):
        out = res.check(sentence, record=False)
        assert all(p.status == "check" for p in _significance_parts(out)), str(out)


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("sentence", [
    "The new method failed to significantly improve scores.",
    "Whether the new method significantly improved scores is unclear.",
    "It is unclear whether the new method significantly improved scores.",
])
def test_negated_or_hedged_significance_is_not_a_conflict(route, sentence):
    out = _result(route, 1.54, 1.35).check(sentence, record=False)
    parts = _significance_parts(out)
    assert parts and all(p.status == "check" for p in parts), str(out)


@pytest.mark.parametrize("route", ["estimate-se, contrast", "scipy, contrast"])
def test_another_named_test_is_not_read_as_the_zero_test(route):
    out = _result(route, 1.54, 1.35).check("For the equivalence test, the result was significant.",
                                          record=False)
    assert all(p.status != "conflict" for p in _significance_parts(out)), str(out)


def test_quick_start_sentence_is_a_conflict():
    new, old = _groups()
    plan = sw.declare(sesoi=3, sesoi_source="smallest score gain teachers said would change their practice",
                      units="points", scope="first-year students, one university, one term")
    res = plan.analyze(stats.ttest_ind(new, old))
    out = res.check("The new method significantly improved scores.", record=False)
    assert out.level == "conflict"
    assert str(out).startswith("[1 conflict, 1 to verify]")
