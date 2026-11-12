"""Compare a real-data model with NIST's independently certified values.

The data are included with statsmodels. NIST certifies the coefficients and
standard errors, not the p-values or intervals below. Those are recomputed
from the certified inputs using SciPy, which statwarrant also uses; they are
not an independent implementation-level validation of every calculation.

Source: https://www.itl.nist.gov/div898/strd/lls/data/LINKS/v-Longley.shtml
"""
import numpy as np
import pytest
from scipy.stats import t
import statsmodels.api as sm

import statwarrant as sw


# NIST: beta(i), standard deviation of estimated beta(i).
CERTIFIED = {
    "const": (-3482258.63459582, 890420.383607373),
    "GNPDEFL": (15.0618722713733, 84.9149257747669),
    "GNP": (-0.0358191792925910, 0.0334910077722432),
    "UNEMP": (-2.02022980381683, 0.488399681651699),
    "ARMED": (-1.03322686717359, 0.214274163161675),
    "POP": (-0.0511041056535807, 0.226073200069370),
    "YEAR": (1829.15146461355, 455.478499142212),
}


@pytest.fixture(scope="module")
def longley_model():
    data = sm.datasets.longley.load_pandas().data
    assert len(data) == 16
    assert data["YEAR"].astype(int).tolist() == list(range(1947, 1963))
    predictors = ["GNPDEFL", "GNP", "UNEMP", "ARMED", "POP", "YEAR"]
    model = sm.OLS(data["TOTEMP"], sm.add_constant(data[predictors])).fit()
    assert model.df_resid == 9 and model.use_t
    return model


@pytest.mark.parametrize("term", CERTIFIED)
def test_longley_regression_against_nist(longley_model, term):
    b, se = CERTIFIED[term]
    evidence = sw.declare().analyze(longley_model, term=term).evidence
    critical = t.isf(.025, df=9)
    expected_ci = (b - critical * se, b + critical * se)
    expected_p = 2 * t.sf(abs(b / se), df=9)
    assert evidence.estimate == pytest.approx(b, rel=1e-6, abs=1e-8)
    assert evidence.se == pytest.approx(se, rel=1e-6, abs=1e-8)
    assert evidence.zero_interval == pytest.approx(expected_ci, rel=1e-6, abs=1e-8)
    assert evidence.p_zero == pytest.approx(expected_p, rel=1e-6, abs=1e-8)


def test_longley_unemployment_threshold_example(longley_model):
    """The bound is hypothetical and not an economic importance threshold."""
    b, se = CERTIFIED["UNEMP"]
    alpha, d, df = .05, 2., 9
    result = sw.declare(
        sesoi=d,
        sesoi_source="Illustrative test threshold, not a validated economic criterion",
        interval_policy="standard",
    ).analyze(longley_model, term="UNEMP")
    e = result.evidence
    p_zero = 2 * t.sf(abs(b / se), df)
    p_equivalence = max(t.sf((b + d) / se, df), t.cdf((b - d) / se, df))
    p_minimal_effect = min(t.cdf((b + d) / se, df), t.sf((b - d) / se, df))
    assert e.p_zero == pytest.approx(p_zero, rel=1e-6)
    assert e.p_equivalence == pytest.approx(p_equivalence, rel=1e-6)
    assert e.p_minimal_effect == pytest.approx(p_minimal_effect, rel=1e-6)
    assert e.differs_from_zero == (p_zero < alpha)
    assert e.equivalent == (p_equivalence < alpha)
    assert e.exceeds_sesoi == (p_minimal_effect < alpha / 2)
    assert result.thresholds.decision(d) == "undetermined"
