"""Targeted regressions for observed adapter safety and provenance issues."""
import json
import math
from decimal import Decimal

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant import adapters
from statwarrant.adapters import AdapterMismatch


class ZResult:
    use_t = False

    def __init__(self, z, p):
        self.params = np.array([z])
        self.bse = np.array([1.0])
        self.tvalues = np.array([z])
        self.pvalues = np.array([p])


def test_zero_p_with_ordinary_computed_probability_is_rejected():
    with pytest.raises(AdapterMismatch, match="reports p = 0"):
        sw.declare().analyze(ZResult(1.0, 0.0), term=0)


@pytest.mark.parametrize("p", [Decimal("1e-400"), Decimal("-1e-400"), "1e-400", "-1e-400"])
def test_nonzero_source_p_cannot_silently_narrow_to_zero(p):
    with pytest.raises(AdapterMismatch, match="nonzero p-value"):
        sw.declare().analyze(ZResult(40.0, p), term=0)


def test_extended_precision_source_p_does_not_silently_narrow_to_zero():
    p = np.longdouble("1e-400")
    if p == 0:
        pytest.skip("longdouble has no additional exponent range on this platform")
    with pytest.raises(AdapterMismatch, match="nonzero p-value"):
        sw.declare().analyze(ZResult(40.0, p), term=0)


@pytest.mark.parametrize("z", [30.0, 34.0, 40.0])
def test_tiny_source_zero_is_accepted_only_with_honest_note(z):
    result = sw.declare().analyze(ZResult(z, 0.0), term=0)
    note = " ".join(result.raw_input["provenance_notes"]).lower()
    assert "reports p = 0" in note
    assert "could" in note and "underflow" in note
    assert "error" in note and "could not be verified" in note
    assert "an underflow" not in note
    assert result.raw_input["reported_p"] == 0.0
    assert result.evidence.p_zero == pytest.approx(2 * stats.norm.sf(z))


def test_positive_p_with_underflowed_sf_is_checked_using_logsf():
    z = 37.7
    expected = math.exp(math.log(2.0) + stats.norm.logsf(z))
    assert expected > 0 and 2 * stats.norm.sf(z) == 0
    result = sw.declare().analyze(ZResult(z, expected), term=0)
    assert result.evidence.p_zero == expected
    assert result.raw_input["reported_p"] == expected
    with pytest.raises(AdapterMismatch):
        sw.declare().analyze(ZResult(z, 1e-300), term=0)
    with pytest.raises(AdapterMismatch):
        sw.declare().analyze(ZResult(40.0, 1e-300), term=0)


def test_subnormal_rounding_is_respected_without_hiding_mismatch():
    z = 38.5
    expected = math.exp(math.log(2.0) + stats.norm.logsf(z))
    assert expected == math.ulp(0.0)
    sw.declare().analyze(ZResult(z, expected), term=0)
    with pytest.raises(AdapterMismatch):
        sw.declare().analyze(ZResult(40.0, expected), term=0)


def test_unavailable_log_tail_is_disclosed_not_silently_verified(monkeypatch):
    class UnavailableTail:
        @staticmethod
        def sf(x):
            return 0.0

        @staticmethod
        def logsf(x):
            return -math.inf

    monkeypatch.setattr(adapters, "_dist", lambda df: UnavailableTail())
    result = sw.declare().analyze(ZResult(40.0, 1e-300), term=0)
    assert "unverified" in " ".join(result.raw_input["provenance_notes"]).lower()


def test_student_t_extreme_positive_p_uses_the_declared_reference():
    class TResult(ZResult):
        use_t = True
        df_resid = 10000

    z = 38.0
    expected = 2 * stats.t.sf(z, 10000)
    assert 0 < expected < 1e-250
    result = sw.declare().analyze(TResult(z, expected), term=0)
    assert result.evidence.df == 10000
    with pytest.raises(AdapterMismatch):
        sw.declare().analyze(TResult(z, 1e-260), term=0)


@pytest.mark.parametrize("source_null,x,rel", [
    (1e-8, 1e6 + np.tile([-50000.0, 50000.0], 50), .02),
    (1e-5, 1e9 + np.tile([-1.0, 1.0], 50) * 2e-5, .02),
    (.5, 1e14 + np.array([-.325, -.275, -.175, -.025, .175, .425, .725, -.25, .15, .6]), .02),
])
def test_reconstructable_nonzero_scipy_null_is_not_zero(source_null, x, rel):
    result = sw.declare().analyze(stats.ttest_1samp(x, source_null))
    assert result.null == pytest.approx(source_null, rel=rel)
    assert json.loads(result.to_json())["null_value"] == result.null
    notes = " ".join(result.raw_input["provenance_notes"]).lower()
    assert "null" in notes and "approximately" in notes and "rounding" in notes


def test_unresolvable_null_is_unknown_not_zero_in_json_and_markdown():
    # In binary64 this small nonzero null rounds away in SciPy's subtraction.
    x = 1e14 + np.array([-.325, -.275, -.175, -.025, .175, .425, .725, -.25, .15, .6])
    result = sw.declare().analyze(stats.ttest_1samp(x, 0.001))
    assert result.null is None
    data = json.loads(result.to_json())
    assert data["null_value"] is None
    assert "unknown" in data["input"].lower()
    assert "unknown" in " ".join(data["raw_input"]["provenance_notes"]).lower()
    assert "unknown" in result.to_markdown().lower()


def test_ordinary_zero_and_nonzero_nulls_remain_usable():
    x = np.array([99., 100., 101., 102., 103.])
    zero = sw.declare().analyze(stats.ttest_1samp(x, 0))
    assert zero.null == 0.0
    assert json.loads(zero.to_json())["null_value"] == 0.0
    note = " ".join(zero.raw_input["provenance_notes"]).lower()
    assert "inferred" in note and "nonzero" in note and "cannot be ruled out" in note
    nonzero = sw.declare().analyze(stats.ttest_1samp(x, 100))
    assert nonzero.null == pytest.approx(100)
    assert nonzero.evidence.estimate == pytest.approx(1)
    assert "null value 100" in nonzero.source


def test_float32_scipy_roundoff_is_not_mistaken_for_a_known_nonzero_null():
    x = np.random.default_rng(42).normal(size=100).astype(np.float32)
    zero = sw.declare().analyze(stats.ttest_1samp(x, np.float32(0)))
    assert zero.null is None or zero.null == 0.0
    assert "rounding" in " ".join(zero.raw_input["provenance_notes"]).lower()
    nonzero = sw.declare().analyze(stats.ttest_1samp(x, np.float32(.2)))
    assert nonzero.null == pytest.approx(.2, abs=1e-6)
    assert "rounding" in " ".join(nonzero.raw_input["provenance_notes"]).lower()


@pytest.mark.parametrize("make", [list, lambda x: np.asarray(x, dtype=object)])
def test_mixed_sign_integers_are_subtracted_before_array_inference(make):
    base = 2**63
    a, b = make([base + 1, -1, base + 3, -3]), make([base, -2, base, -6])
    assert adapters.paired_differences(a, b).tolist() == [1, 1, 3, 3]
    result = sw.declare().analyze_paired(a, b)
    reference = sw.declare().analyze_paired([1, 1, 3, 3], [0, 0, 0, 0])
    assert result.evidence.estimate == reference.evidence.estimate == 2
    assert result.evidence.se == pytest.approx(reference.evidence.se)
    assert result.evidence.p_zero == pytest.approx(reference.evidence.p_zero)
    assert result.raw_input["n_differing_items"] == 4


def test_mixed_numeric_types_subtract_before_conversion_and_allow_clusters():
    base = 2**63
    a = [base + 1, -1.5, np.uint64(base + 3), Decimal("-2.5")]
    b = [float(base), -2.5, base, -5.5]
    assert adapters.paired_differences(a, b).tolist() == [1, 1, 3, 3]
    result = sw.declare().analyze_paired(a, b, cluster=["a", "a", "b", "b"])
    ref = sw.declare().analyze_paired([1, 1, 3, 3], [0, 0, 0, 0], cluster=["a", "a", "b", "b"])
    assert result.evidence.estimate == ref.evidence.estimate
    assert result.evidence.se == ref.evidence.se
    assert result.raw_input["n_clusters"] == 2
    json.loads(result.to_json())


def test_huge_integers_can_cancel_before_float_conversion():
    big = 10**400
    assert adapters.paired_differences([big + 1, -big + 3], [big, -big]).tolist() == [1.0, 3.0]


@pytest.mark.parametrize("cluster", [None, [0, 1, 2, 3]])
def test_finite_differences_with_unrepresentable_aggregate_are_refused(cluster):
    a = [1e308, 1e308, -1e308, -1e308]
    b = [0.0] * 4
    with pytest.raises(ValueError, match="finite"):
        adapters.paired(a, b, cluster=cluster)
    with pytest.raises(ValueError, match="finite"):
        sw.declare().analyze_paired(a, b, cluster=cluster)


@pytest.mark.parametrize("a,b", [
    ([float("nan"), 1], [0, 0]),
    ([float("inf"), 1], [0, 0]),
    ([10**400, 1], [0, 0]),
    ([2**63 + 1, 1], [0, 0]),
    ([Decimal("1e-400"), 1], [0, 0]),
    ([1, 2], [0]),
    ([[1], [2]], [[0], [0]]),
])
def test_bad_or_unrepresentable_scores_are_safely_refused(a, b):
    with pytest.raises(ValueError):
        adapters.paired_differences(a, b)


def test_finite_input_floats_already_rounded_before_entry_cannot_be_recovered():
    big = 2**63
    # These two floats are equal before the adapter sees them.
    assert float(big + 1) == float(big)
    assert adapters.paired_differences([float(big + 1), 2.], [float(big), 0.]).tolist() == [0., 2.]


def test_longley_statsmodels_example_still_works():
    sm = pytest.importorskip("statsmodels.api")
    data = sm.datasets.longley.load_pandas()
    fit = sm.OLS(data.endog, sm.add_constant(data.exog)).fit()
    res = sw.declare().analyze(fit, term="GNPDEFL")
    assert res.evidence.estimate == pytest.approx(fit.params["GNPDEFL"])
    assert res.evidence.se == pytest.approx(fit.bse["GNPDEFL"])
    assert res.evidence.p_zero == pytest.approx(fit.pvalues["GNPDEFL"])
    json.loads(res.to_json())
