"""Structured assertions are judged by the same tests as the claim contract."""

import pytest

import statwarrant as sw
from statwarrant import Assertion


def _res(est, se=1.6, df=58, design=None, sesoi=3):
    kw = {} if sesoi is None else {"sesoi": sesoi, "sesoi_source": "smallest gain teachers act on"}
    plan = sw.declare(units="points", scope="first-year students, one university", outcome="exam score",
                      contrast="new method minus existing method", design=design, **kw)
    return plan.analyze(estimate=est, se=se, df=df)


def st(res, **kw):
    return res.verify(Assertion(**kw)).status


def test_significance_and_direction():
    pos, null = _res(4.2), _res(1.0)
    assert st(pos, kind="nonzero") == "supported"
    assert st(pos, kind="nonzero", direction="positive") == "supported"
    assert st(pos, kind="nonzero", direction="negative") == "contradicted"
    assert st(null, kind="nonzero") == "not_established"


def test_no_effect_is_never_supported():
    assert st(_res(4.2), kind="no_effect") == "contradicted"
    assert st(_res(1.0), kind="no_effect") == "not_established"
    eq = _res(0.1, se=0.5)
    assert eq.evidence.equivalent
    v = eq.verify(Assertion(kind="no_effect"))
    assert v.status == "not_established" and "say that instead" in v.reason


def test_importance_and_equivalence():
    assert st(_res(4.2), kind="important") == "not_established"
    assert st(_res(9.0), kind="important", direction="positive") == "supported"
    assert st(_res(9.0), kind="important", direction="negative") == "contradicted"
    assert st(_res(9.0), kind="equivalent") == "contradicted"
    assert st(_res(0.1, se=0.5), kind="equivalent") == "supported"
    assert st(_res(0.1, se=0.5), kind="important") == "contradicted"
    assert st(_res(4.2, sesoi=None), kind="important") == "not_established"


def test_size_bounds():
    res = _res(4.2)  # 95% CI about [1.0, 7.4]
    assert st(res, kind="at_least", value=0.5, direction="positive") == "supported"
    assert st(res, kind="at_least", value=3, direction="positive") == "not_established"
    assert st(res, kind="at_least", value=8, direction="positive") == "contradicted"
    assert st(res, kind="at_least", value=3, direction="negative") == "contradicted"
    assert st(res, kind="at_most", value=8, direction="positive") == "supported"
    assert st(res, kind="at_most", value=0.5, direction="positive") == "contradicted"
    assert st(res, kind="at_least", value=3) == "not_established"  # either direction
    assert st(res, kind="about", value=4) == "to_verify"
    assert st(res, kind="about", value=9) == "contradicted"


def test_causal_and_generalization():
    assert st(_res(4.2, design="observational"), kind="causal") == "contradicted"
    assert st(_res(4.2, design="randomised"), kind="causal") == "to_verify"
    assert st(_res(1.0, design="randomised"), kind="causal") == "not_established"
    assert st(_res(4.2), kind="generalization") == "not_established"


def test_denials_and_hedges_are_never_cleared():
    res = _res(4.2)
    assert st(res, kind="nonzero", polarity="denied") == "contradicted"
    assert st(res, kind="important", polarity="denied") == "to_verify"
    assert st(res, kind="important", polarity="hedged") == "to_verify"


def test_dicts_are_accepted_and_bad_input_refused():
    res = _res(4.2)
    v = res.verify({"kind": "nonzero", "direction": "unclear", "quote": "improved"})
    assert v.status == "supported" and v.assertion.direction is None
    assert v.to_dict()["assertion"]["quote"] == "improved"
    with pytest.raises(ValueError):
        Assertion(kind="proves")
    with pytest.raises(ValueError):
        Assertion(kind="at_least")
    with pytest.raises(ValueError):
        Assertion(kind="nonzero", direction="up")


def test_verdicts_agree_with_the_claim_contract():
    # what the contract blocks is never "supported"; what it allows about importance is
    for est, se in [(4.2, 1.6), (9.0, 1.6), (0.1, 0.5), (1.0, 1.6), (-9.0, 1.6)]:
        res = _res(est, se=se)
        blocked = {c.category for c in res.claims.blocked}
        if "no-effect" in blocked:
            assert st(res, kind="no_effect") != "supported"
        if "importance" in blocked:
            assert st(res, kind="important") != "supported"
        if "equivalence" in blocked:
            assert st(res, kind="equivalent") != "supported"
        if res.evidence.claim_class.startswith("exceeds_sesoi"):
            assert st(res, kind="important") == "supported"
