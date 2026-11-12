"""Regression tests for extreme p-values and honest comparison/reporting."""
import json
import math
import sys

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant import adapters
from statwarrant._core import evaluate
from statwarrant.adapters import AdapterMismatch


@pytest.mark.parametrize("policy", ["single", "standard"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_reported_normal_example_is_recovered(policy, sign):
    result = sw.declare(interval_policy=policy).analyze(estimate=sign * 37.7, se=1)
    p = math.exp(math.log(2) + stats.norm.logsf(37.7))
    assert 2 * stats.norm.sf(37.7) == 0
    assert result.evidence.p_zero == p == 4.9669706205543e-311
    assert result.evidence.differs_from_zero
    assert result.check("p < 1e-320", record=False).level == "conflict"
    assert result.check("p <= 1e-320", record=False).level == "conflict"
    assert result.check("p > 1e-320", record=False).level is None
    assert result.check("p >= 1e-320", record=False).level is None
    assert result.check("p = 5e-311", record=False).level is None
    assert result.check("p = 1e-320", record=False).level == "conflict"
    assert result.check("p = 0", record=False).level == "conflict"
    assert result.evidence.to_dict()["zero_test"].get("p_value_underflow_or_unavailable") is None
    assert "underflow" not in result.to_markdown().lower()


@pytest.mark.parametrize("policy", ["single", "standard"])
@pytest.mark.parametrize("df,x,expected", [
    # Reference from high-precision regularized incomplete beta, I_(df/(df+x*x))(df/2, 1/2).
    (1e8, 38.0, 5.8010594e-316),
    # For df=2, p = 1 - x/sqrt(x*x+2) ~ 1/x**2.
    (2.0, 1e160, 1e-320),
    # Cauchy two-sided tail is 2*atan(1/x)/pi.
    (1.0, 1e308, 2 / math.pi / 1e308),
])
def test_student_t_recovers_tails_where_scipy_logsf_also_underflows(policy, df, x, expected):
    assert stats.t.sf(x, df) == 0
    assert stats.t.logsf(x, df) == -math.inf
    result = sw.declare(interval_policy=policy).analyze(estimate=x, se=1, df=df)
    assert result.evidence.p_zero > 0
    # Subnormals have an absolute quantization error of at least one ulp.
    assert abs(result.evidence.p_zero - expected) <= max(2 * math.ulp(expected), expected * 1e-11)
    assert result.check("p > 0", record=False).level is None
    assert result.check("p = 0", record=False).level == "conflict"


@pytest.mark.parametrize("policy", ["single", "standard"])
@pytest.mark.parametrize("df,stat", [(None, 37.7), (1e8, 38.0)])
def test_one_sided_named_tails_are_recovered(policy, df, stat):
    dist = stats.norm if df is None else stats.t(df)
    assert dist.sf(stat) == 0
    two = sw.declare(interval_policy=policy).analyze(estimate=stat, se=1, df=df).evidence.p_zero
    eq = sw.declare(sesoi=stat, sesoi_source="test", interval_policy=policy).analyze(estimate=0, se=1, df=df)
    met = sw.declare(sesoi=1, sesoi_source="test", interval_policy=policy).analyze(estimate=stat + 1, se=1, df=df)
    for result, name, p in [(eq, "equivalence", eq.evidence.p_equivalence),
                            (met, "minimal-effect", met.evidence.p_minimal_effect)]:
        assert p > 0
        assert abs(2 * p - two) <= 2 * math.ulp(two)
        assert result.check(f"The {name} test gave p > 1e-320", record=False).level is None
        assert result.check(f"The {name} test gave p < 1e-320", record=False).level == "conflict"
        assert result.check(f"The {name} test gave p = 0", record=False).level == "conflict"


@pytest.mark.parametrize("policy", ["single", "standard"])
@pytest.mark.parametrize("name", ["zero", "equivalence", "minimal-effect"])
@pytest.mark.parametrize("df,x", [(None, 40), (1e8, 40), (10, 1e40)])
def test_genuine_underflow_is_a_check_and_is_disclosed(policy, name, df, x):
    if name == "zero":
        result = sw.declare(interval_policy=policy).analyze(estimate=x, se=1, df=df)
        value, field, prefix = result.evidence.p_zero, "zero_test", ""
    elif name == "equivalence":
        result = sw.declare(sesoi=x, sesoi_source="test", interval_policy=policy).analyze(estimate=0, se=1, df=df)
        value, field, prefix = result.evidence.p_equivalence, "equivalence_test", "The equivalence test gave "
    else:
        # A small bound cannot be distinguished from x at very large x; that is harmless here.
        result = sw.declare(sesoi=1, sesoi_source="test", interval_policy=policy).analyze(estimate=x, se=1, df=df)
        value, field, prefix = result.evidence.p_minimal_effect, "minimal_effect_test", "The minimal-effect test gave "
    assert value == 0
    for comparison in ["p < 1e-320", "p <= 1e-320", "p > 1e-320", "p >= 1e-320", "p = 1e-320", "p = 0"]:
        checked = result.check(prefix + comparison, record=False)
        assert checked.level == "check", str(checked)
        assert "not exact" in checked.warnings[0].reason
    data = json.loads(result.to_json())
    assert data["evidence"][field]["p_value"] == 0
    assert data["evidence"][field]["p_value_underflow_or_unavailable"] is True
    assert "underflow" in " ".join(data["claims"]["notes"]).lower()
    report = result.to_markdown().lower()
    assert "underflow" in report and "not exact zero" in report
    assert "stored zero is not an exact probability" in report


@pytest.mark.parametrize("literal", ["1e-400", "1e-324", "3e-324", "4e-324", "1e+400"])
@pytest.mark.parametrize("op", ["=", "<", "<=", ">", ">="])
def test_nonrepresentable_written_thresholds_need_review(literal, op):
    # In particular 3e-324 rounds UP to min-subnormal, not to zero.
    result = sw.declare().analyze(estimate=37.7, se=1)
    check = result.check(f"p {op} {literal}", record=False)
    assert check.level == "check", str(check)
    assert "represent" in check.warnings[0].reason


def test_subnormal_boundary_inequalities_are_not_guessed():
    minimum = math.ulp(0.0)
    result = sw.declare().analyze(estimate=38.5, se=1)
    assert result.evidence.p_zero == minimum
    assert result.check("p = 5e-324", record=False).level is None
    for op in ["<", "<=", ">", ">="]:
        assert result.check(f"p {op} 5e-324", record=False).level == "check"
    assert result.check("p < 1e-320", record=False).level is None
    assert result.check("p > 1e-320", record=False).level == "conflict"
    assert sw.declare().analyze(estimate=38.55, se=1).evidence.p_zero == 0


def test_subnormal_t_tail_approximation_cannot_reverse_a_close_inequality():
    # High-precision incomplete beta is 9.99999999999984e-309 for this
    # binary64 statistic. Quadrature may round slightly above 1e-308.
    result = sw.declare().analyze(estimate=37.55925377476744, se=1, df=1e8)
    assert 0 < result.evidence.p_zero < sys.float_info.min
    for op in ["<", "<=", ">", ">="]:
        assert result.check(f"p {op} 1e-308", record=False).level == "check"
    assert result.check("p < 1e-300", record=False).level is None
    assert result.check("p > 1e-300", record=False).level == "conflict"


def test_recovered_normal_p_from_subnormal_tail_also_gets_a_guard():
    result = sw.declare().analyze(estimate=37.537086746862656, se=1, df=1e8)
    assert sys.float_info.min < result.evidence.p_zero < 2 * sys.float_info.min
    for op in ["<", "<=", ">", ">="]:
        assert result.check(f"p {op} 2.3e-308", record=False).level == "check"
    assert result.check("p < 1e-300", record=False).level is None


@pytest.mark.parametrize("df", [None, 20, 10000])
@pytest.mark.parametrize("policy", ["single", "standard"])
@pytest.mark.parametrize("z", [0, 1.96, 8, 20, 35])
def test_ordinary_and_naturally_small_p_values_and_decisions_are_unchanged(df, policy, z):
    dist = stats.norm if df is None else stats.t(df)
    ev = evaluate(z, 1, df, 0.05, policy, (-1.0, 1.0))
    assert 2 * dist.sf(z) >= sys.float_info.min
    assert ev.p_zero == min(1.0, 2 * dist.sf(z))
    assert ev.p_equivalence == max(dist.sf(z + 1), dist.sf(1 - z))
    assert ev.p_minimal_effect == min(dist.sf(z - 1), dist.sf(-z - 1))
    assert ev.differs_from_zero == (z > dist.isf(.025))
    assert ev.equivalent == (z + 1 > dist.isf(.025 if policy == "single" else .05)
                             and 1 - z > dist.isf(.025 if policy == "single" else .05))
    assert ev.exceeds_sesoi == (z - 1 > dist.isf(.025))


class ModelResult:
    def __init__(self, x, p, df=None):
        self.params = np.array([x])
        self.bse = np.array([1.0])
        self.tvalues = np.array([x])
        self.pvalues = np.array([p])
        self.use_t = df is not None
        self.df_resid = df


@pytest.mark.parametrize("x,df", [(37.7, None), (38.0, 1e8)])
def test_adapter_matches_recovered_positive_tails_and_rejects_wrong_p(x, df):
    expected = sw.declare().analyze(estimate=x, se=1, df=df).evidence.p_zero
    result = sw.declare().analyze(ModelResult(x, expected, df), term=0)
    assert result.evidence.p_zero == expected
    assert result.raw_input["reported_p"] == expected
    assert result.check("p > 1e-320", record=False).level is None
    with pytest.raises(AdapterMismatch):
        sw.declare().analyze(ModelResult(x, 1e-300, df), term=0)


@pytest.mark.parametrize("x,df", [(40.0, None), (40.0, 1e8)])
def test_adapter_zero_source_does_not_claim_exact_zero(x, df):
    result = sw.declare().analyze(ModelResult(x, 0, df), term=0)
    assert result.evidence.p_zero == 0
    note = " ".join(result.raw_input["provenance_notes"]).lower()
    assert "unverified" in note or "could not be verified" in note
    assert "not an exact zero" in note
    assert result.check("p < 1e-320", record=False).level == "check"
    assert "not exact zero" in result.to_markdown().lower()


def test_unavailable_reference_tail_is_not_silently_verified(monkeypatch):
    class Unavailable:
        def sf(self, x):
            return 0.0

        def logsf(self, x):
            return -math.inf

    monkeypatch.setattr(adapters, "_dist", lambda df: Unavailable())
    note = adapters._verify(40, 1, None, 40, 1e-300, "source")
    assert "unverified" in note


def test_unavailable_t_fallback_never_asserts_an_inequality(monkeypatch):
    from statwarrant import _core

    monkeypatch.setattr(_core, "_log_t_tail", lambda x, df: -math.inf)
    result = sw.declare().analyze(estimate=38, se=1, df=1e8)
    assert result.evidence.p_zero == 0
    assert result.check("p < 1e-320", record=False).level == "check"
    assert result.check("p > 1e-320", record=False).level == "check"
    assert result.evidence.to_dict()["zero_test"]["p_value_underflow_or_unavailable"]
    assert "unavailable" in result.to_markdown().lower()
