"""Checks for unreliable critical values in extreme Student-t tails."""
import math
import pytest
from scipy import stats
import statwarrant as sw
from statwarrant._core import critical_value


@pytest.mark.parametrize("df", [1e-6, 0.0001, 0.001])
def test_tiny_df_does_not_create_false_significance(df):
    # Some SciPy t.isf implementations return a finite value whose own sf is
    # nowhere near 0.025. Refuse the result instead of claiming significance.
    q = stats.t.isf(0.025, df)
    if abs(stats.t.sf(q, df) - .025) < .025e-6:
        pytest.skip("installed SciPy computes a self-consistent critical value")
    with pytest.raises(ValueError, match="critical value"):
        sw.declare().analyze(estimate=1e308, se=1, df=df)
    with pytest.raises(ValueError, match="critical value"):
        critical_value(.95, df)


@pytest.mark.parametrize("df", [.01, .1, 1, 3, 58, None])
def test_consistent_critical_values_remain_available(df):
    dist = stats.norm if df is None else stats.t(df)
    raw = float(dist.isf(.025))
    if not math.isfinite(raw) or not math.isclose(float(dist.sf(raw)), .025, rel_tol=1e-6):
        # Older SciPy versions may also fail at df=.01; conservative refusal is correct.
        with pytest.raises(ValueError, match="critical value"):
            critical_value(.95, df)
    else:
        q = critical_value(.95, df)
        assert dist.sf(q) == pytest.approx(.025, rel=1e-6)
