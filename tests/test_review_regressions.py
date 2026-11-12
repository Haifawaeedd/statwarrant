"""Regression tests for the external review of statwarrant 0.1.0.

Each test reproduces one example from the review and checks the corrected behaviour.
"""

import json
import math

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant._core import evaluate
from statwarrant.adapters import AdapterMismatch


# 1. statsmodels cluster-robust errors: use statsmodels' own inference df (G - 1).
def test_statsmodels_cluster_df_follows_statsmodels():
    sm = pytest.importorskip("statsmodels.api")
    groups = np.repeat(np.arange(4), 10)
    y = np.repeat([0.0, 1.0, 2.0, 3.0], 10)
    fit = sm.OLS(y, np.ones((40, 1))).fit(cov_type="cluster", cov_kwds={"groups": groups}, use_t=True)
    ev = sw.declare().analyze(fit, term=0).evidence
    assert ev.df == 3
    assert ev.p_zero == pytest.approx(fit.pvalues[0], rel=1e-9)
    assert ev.p_zero == pytest.approx(0.1027, abs=1e-4)
    assert ev.zero_interval == pytest.approx(tuple(fit.conf_int()[0]), rel=1e-9)
    assert not ev.differs_from_zero


@pytest.mark.parametrize("cov_type,kwargs", [("nonrobust", {}), ("HC3", {}), ("HC1", {"use_t": True})])
def test_statsmodels_p_values_reproduced(cov_type, kwargs):
    sm = pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(11)
    x = rng.normal(size=60)
    y = 0.3 * x + rng.normal(size=60)
    fit = sm.OLS(y, sm.add_constant(x)).fit(cov_type=cov_type, **kwargs)
    ev = sw.declare().analyze(fit, term=1).evidence
    assert ev.p_zero == pytest.approx(fit.pvalues[1], rel=1e-9)


def test_statsmodels_glm_uses_normal_reference():
    sm = pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(12)
    x = rng.normal(size=200)
    yb = (rng.uniform(size=200) < 1 / (1 + np.exp(-0.5 * x))).astype(float)
    fit = sm.GLM(yb, sm.add_constant(x), family=sm.families.Binomial()).fit()
    ev = sw.declare().analyze(fit, term=1).evidence
    assert ev.df is None
    assert ev.p_zero == pytest.approx(fit.pvalues[1], rel=1e-9)


def test_adapter_refuses_a_result_it_cannot_reproduce():
    class FakeFit:
        params = np.array([1.0])
        bse = np.array([0.5])
        use_t = True
        df_resid = 30.0
        pvalues = np.array([0.5])  # inconsistent with est / se / df

    with pytest.raises(AdapterMismatch):
        sw.declare().analyze(FakeFit(), term=0)


# 2. An asymmetric interval is refused instead of silently symmetrised.
def test_asymmetric_interval_is_refused():
    with pytest.raises(ValueError, match="not symmetric"):
        sw.declare().analyze(estimate=1.5, ci=(-0.1, 2.2))


# 3. scipy one-sample test against a non-zero popmean.
def test_ttest_1samp_against_nonzero_popmean():
    t = stats.ttest_1samp([99, 100, 101, 102, 103], 100)
    res = sw.declare().analyze(t)
    ev = res.evidence
    assert ev.estimate == pytest.approx(1.0)
    assert ev.p_zero == pytest.approx(t.pvalue, rel=1e-9)  # about 0.230, not 1.4e-8
    assert not ev.differs_from_zero
    assert "null value 100" in res.source
    assert any("null value 100" in n for n in res.claims.notes)
    assert json.loads(res.to_json())["null_value"] == 100


def test_ttest_1samp_zero_null_unchanged():
    rng = np.random.default_rng(13)
    x = rng.normal(0.5, 1, 30)
    t = stats.ttest_1samp(x, 0)
    res = sw.declare().analyze(t)
    assert res.evidence.estimate == pytest.approx(x.mean(), rel=1e-9)
    assert res.null == 0.0


# 4. Minimal-effect test: type I error at most alpha under both policies.
@pytest.mark.parametrize("policy", ["single", "standard"])
@pytest.mark.parametrize("width", [0.01, 0.1, 0.2, 1.0, 3.0])
def test_minimal_effect_type_one_error_at_most_alpha(policy, width):
    se, alpha = 1.0, 0.05
    low, high = -width / 2, width / 2
    # exact rejection probability when the true effect sits on the upper bound
    ev = evaluate(0.0, se, None, alpha, policy, (low, high))
    c = stats.norm.ppf(1 - ev.met_threshold)
    size = stats.norm.sf(c) + stats.norm.cdf(-c - (high - low) / se)
    assert size <= alpha + 1e-12


def test_minimal_effect_size_by_simulation():
    rng = np.random.default_rng(14)
    draws = rng.normal(0.1, 1.0, 20000)  # true effect on the bound
    rejected = np.mean([evaluate(x, 1.0, None, 0.05, "standard", (-0.1, 0.1)).exceeds_sesoi for x in draws])
    assert rejected < 0.05 + 3 * math.sqrt(0.05 * 0.95 / 20000)


# 5. Sentence checker: these used to pass without a warning.
@pytest.fixture
def tight():
    return sw.declare(sesoi=0.2, sesoi_source="review example").analyze(estimate=0.21, se=0.001)


@pytest.mark.parametrize("sentence", [
    "There was no increase in scores.",
    "The effect is negative and statistically significant.",
    "Scores increased for every student.",
])
def test_review_sentences_are_blocked(tight, sentence):
    assert tight.check(sentence).level == "conflict"


def test_unverified_large_number_is_blocked():
    res = sw.declare(sesoi=3, sesoi_source="teachers", units="points").analyze(estimate=4.2, se=1.6, df=58)
    assert res.check("The new method improved scores by 100 points.").level == "conflict"
    assert res.check("The new method improved scores by about 4 points.").status == "no_warnings"


def test_numbers_that_cannot_be_matched_are_never_allowed():
    res = sw.declare(sesoi=3, sesoi_source="teachers").analyze(estimate=4.2, se=1.6, df=58)
    assert res.check("Scores increased in 120 students.").level == "check"


# 6. Size adjectives are not the same claim as "exceeds the SESOI".
@pytest.mark.parametrize("word", ["huge", "large", "dramatic", "massive", "substantial"])
def test_size_adjectives_need_care_even_when_sesoi_is_exceeded(tight, word):
    assert tight.check(f"The treatment had a {word} effect.").level == "check"


def test_importance_wording_is_allowed_when_sesoi_is_exceeded(tight):
    assert tight.check("The improvement is practically important.").status == "no_warnings"


# Smaller items.
def test_baseline_zero_is_refused():
    with pytest.raises(ValueError, match="non-zero"):
        sw.declare().analyze(estimate=1, se=1, baseline=0)
    with pytest.raises(ValueError):
        sw.declare().analyze(estimate=1, se=1, baseline=float("nan"))


def test_nan_df_and_infinite_sesoi_are_refused():
    with pytest.raises(ValueError):
        sw.declare().analyze(estimate=1, se=1, df=float("nan"))
    with pytest.raises(ValueError):
        sw.declare(sesoi=(-np.inf, np.inf), sesoi_source="x")


def test_fingerprint_is_stable_and_excludes_the_timestamp():
    a = sw.declare(sesoi=3, sesoi_source="teachers", units="points")
    b = sw.declare(sesoi=3, sesoi_source="teachers", units="points")
    c = sw.declare(sesoi=4, sesoi_source="teachers", units="points")
    assert a.fingerprint == b.fingerprint != c.fingerprint
    assert len(a.fingerprint) == 64
    assert a.to_dict()["fingerprint"] == a.fingerprint


# 0.3.0: report fields from the "claim passport" proposal.
def test_passport_fields_and_schema():
    plan = sw.declare(sesoi=3, sesoi_source="teachers", units="points", outcome="exam score",
                      contrast="new method minus existing method", scope="one university",
                      registration="https://osf.io/abcde")
    res = plan.analyze(estimate=4.2, se=1.6, df=58, label="H1")
    d = json.loads(res.to_json())
    assert d["schema"] == "statwarrant-result/2" and d["statwarrant_version"] == sw.__version__
    assert d["label"] == "H1" and d["plan"]["outcome"] == "exam score"
    assert d["thresholds"]["declared_threshold"] == "undetermined"
    assert d["thresholds"]["met_below"] == pytest.approx(0.997, abs=1e-3)
    assert any("causal" in x for x in d["not_verified"])
    assert any("registered with a third party" in x for x in d["not_verified"])  # always, registration or not
    assert any("does not check that it exists" in x for x in d["not_verified"])
    assert d["plan"]["registration_verified"] is False
    md = res.to_markdown()
    assert "Every threshold at once" in md and "Not verified by statwarrant" in md and "H1" in md
    assert res.check("There is no effect.").label == "H1"


def test_registration_link_is_not_part_of_the_fingerprint():
    a = sw.declare(sesoi=3, sesoi_source="t", outcome="score")
    b = sw.declare(sesoi=3, sesoi_source="t", outcome="score", registration="https://osf.io/x")
    c = sw.declare(sesoi=3, sesoi_source="t", outcome="other score")
    assert a.fingerprint == b.fingerprint != c.fingerprint
