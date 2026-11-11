import math
import warnings

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant import adapters


def test_scipy_ttest_ind_round_trip():
    rng = np.random.default_rng(1)
    a, b = rng.normal(0.4, 1, 30), rng.normal(0, 1, 25)
    res = sw.declare().analyze(stats.ttest_ind(a, b))
    assert res.evidence.estimate == pytest.approx(a.mean() - b.mean(), rel=1e-9)
    assert res.evidence.df == 53
    assert res.evidence.p_zero == pytest.approx(stats.ttest_ind(a, b).pvalue, rel=1e-9)
    assert res.source.startswith("scipy:")


def test_scipy_welch_and_paired():
    rng = np.random.default_rng(2)
    a, b = rng.normal(0.4, 1, 30), rng.normal(0, 2, 25)
    welch = stats.ttest_ind(a, b, equal_var=False)
    res = sw.declare().analyze(welch)
    assert res.evidence.p_zero == pytest.approx(welch.pvalue, rel=1e-9)

    x, y = rng.normal(0, 1, 40), rng.normal(0, 1, 40) + 0.3
    rel = stats.ttest_rel(x, y)
    via_scipy = sw.declare().analyze(rel).evidence
    via_paired = sw.declare().analyze_paired(x, y).evidence
    assert via_paired.estimate == pytest.approx(via_scipy.estimate, rel=1e-9)
    assert via_paired.se == pytest.approx(via_scipy.se, rel=1e-9)
    assert via_paired.p_zero == pytest.approx(rel.pvalue, rel=1e-9)


def test_one_sided_scipy_is_rejected():
    rng = np.random.default_rng(3)
    r = stats.ttest_ind(rng.normal(size=20), rng.normal(size=20), alternative="greater")
    with pytest.raises(ValueError, match="two-sided"):
        sw.declare().analyze(r)


def test_unsupported_object():
    with pytest.raises(TypeError):
        sw.declare().analyze(object())


def test_statsmodels_ols_term():
    sm = pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(4)
    x = rng.normal(size=80)
    y = 0.5 * x + rng.normal(size=80)
    fit = sm.OLS(y, sm.add_constant(x)).fit()
    res = sw.declare().analyze(fit, term=1)
    assert res.evidence.estimate == pytest.approx(fit.params[1])
    assert res.evidence.se == pytest.approx(fit.bse[1])
    assert res.evidence.df == pytest.approx(fit.df_resid)
    assert res.evidence.p_zero == pytest.approx(fit.pvalues[1], rel=1e-9)
    with pytest.raises(ValueError):
        sw.declare().analyze(fit)


def test_interval_input_and_asymmetry_warning():
    res = sw.declare().analyze(ci=(1.0, 7.4), df=58)
    assert res.evidence.estimate == pytest.approx(4.2)
    assert res.evidence.se == pytest.approx(3.2 / stats.t.ppf(0.975, 58))
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sw.declare().analyze(estimate=1.5, ci=(1.1, 2.4))
    assert any("log scale" in str(x.message) for x in w)


def test_cluster_se_with_singletons_equals_paired_se():
    rng = np.random.default_rng(5)
    a, b = rng.normal(size=50), rng.normal(size=50)
    plain = adapters.paired(a, b)
    clustered = adapters.paired(a, b, cluster=np.arange(50))
    assert clustered[1] == pytest.approx(plain[1], rel=1e-12)


def test_cluster_se_grows_with_within_cluster_correlation():
    rng = np.random.default_rng(6)
    clusters = np.repeat(np.arange(20), 10)
    shared = np.repeat(rng.normal(0, 1, 20), 10)
    a = shared + rng.normal(0, 0.3, 200)
    b = rng.normal(0, 0.3, 200)
    _, se_plain, _ = adapters.paired(a, b)
    _, se_cl, df = adapters.paired(a, b, cluster=clusters)
    assert se_cl > 2 * se_plain
    assert df == 19


def test_paired_input_errors():
    with pytest.raises(ValueError):
        adapters.paired([1, 2, 3], [1, 2])
    with pytest.raises(ValueError):
        adapters.paired([1, 2], [1, 2], cluster=["a", "a"])
