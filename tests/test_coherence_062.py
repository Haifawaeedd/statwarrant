"""0.6.2: one decision for one proposition (outside review of the 0.6 paper)."""
import math

import pytest
from hypothesis import given, settings, strategies as st

import statwarrant as sw
from statwarrant import Assertion
from statwarrant._core import evaluate


def exam(method):
    return sw.declare(sesoi=3, sesoi_source="illustrative", units="points", better="higher",
                      outcome="exam scores", contrast="the new method minus the standard method",
                      met_method=method).analyze(estimate=6.0, se=1.6, df=58)


@pytest.mark.parametrize("method", ["split", "relevance"])
def test_at_least_the_sesoi_agrees_with_important(method):
    res = exam(method)
    important = res.verify(Assertion("important", direction="positive")).status
    at_least = res.verify(Assertion("at_least", direction="positive", value=3)).status
    assert important == at_least
    sentence = res.check("The new method improved exam scores by at least 3 points.", record=False).level
    assert (sentence == "conflict") == (important != "supported")


def test_relevance_example_supports_both():
    res = exam("relevance")
    assert res.verify(Assertion("at_least", direction="positive", value=3)).status == "supported"
    assert res.check("The new method improved exam scores by at least 3 points.", record=False).level != "conflict"


def test_split_example_leaves_both_open():
    res = exam("split")
    assert res.verify(Assertion("at_least", direction="positive", value=3)).status == "not_established"
    assert res.check("The new method improved exam scores by at least 3 points.", record=False).level == "conflict"


def test_other_sizes_still_use_the_interval():
    res = exam("relevance")
    assert res.verify(Assertion("at_least", direction="positive", value=2)).status == "supported"
    assert res.verify(Assertion("at_least", direction="positive", value=4)).status == "not_established"


def test_asymmetric_bounds_no_longer_exceed_without_the_zero_test():
    ev = evaluate(1.8, 1.0, None, 0.05, "single", (-10, 0.01), "relevance")
    assert not ev.differs_from_zero
    assert not ev.exceeds_sesoi


@settings(max_examples=400, deadline=None)
@given(est=st.floats(-20, 20), se=st.floats(0.05, 5), low=st.floats(0.01, 10), high=st.floats(0.01, 10),
       df=st.one_of(st.none(), st.floats(2, 200)), method=st.sampled_from(["split", "relevance"]))
def test_exceeding_the_sesoi_implies_a_difference_from_zero(est, se, low, high, df, method):
    ev = evaluate(est, se, df, 0.05, "single", (-low, high), method)
    if ev.exceeds_sesoi:
        assert ev.differs_from_zero
        assert math.copysign(1, ev.estimate) == (1 if ev.claim_class.endswith("positive") else -1)
