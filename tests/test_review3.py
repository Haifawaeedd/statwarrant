"""Regression tests for the independent review of statwarrant 0.3.0.

Each test reproduces one example from the review and checks the corrected behaviour.
"""

import json

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw
from statwarrant._core import evaluate
from statwarrant.adapters import AdapterMismatch


# ---- P0: incorrect numerical conclusions ----------------------------------

@pytest.mark.parametrize("missing", [np.nan, None, float("nan")])
def test_missing_cluster_labels_are_refused(missing):
    x = np.repeat([0.0, 1.0, 2.0, 3.0], 10)
    labels = list(np.repeat([0, 1, 2, 3], 10).astype(float))
    for i in (5, 15, 25, 35):  # missing across several real clusters
        labels[i] = missing
    with pytest.raises(ValueError, match="missing"):
        sw.declare().analyze_paired(x, np.zeros(40), cluster=labels)


def test_missing_cluster_labels_pandas_na():
    pd = pytest.importorskip("pandas")
    labels = pd.Series([0, 0, 1, 1, pd.NA, 2], dtype="object")
    with pytest.raises(ValueError, match="missing"):
        sw.declare().analyze_paired([1.0, 2, 3, 4, 5, 6], [0.0] * 6, cluster=labels)


def test_complete_cluster_labels_unchanged():
    x = np.repeat([0.0, 1.0, 2.0, 3.0], 10)
    e = sw.declare().analyze_paired(x, np.zeros(40), cluster=np.repeat([0, 1, 2, 3], 10)).evidence
    assert (round(e.se, 6), e.df, round(e.p_zero, 6)) == (0.645497, 3.0, 0.102728)


@pytest.mark.parametrize("scale", [1e-9, 1e-3, 1.0, 1e6])
def test_scipy_null_is_recovered_at_every_scale(scale):
    x = np.linspace(1.8, 2.2, 100) * scale
    popmean = 0.8 * scale
    t = stats.ttest_1samp(x, popmean)
    plan = sw.declare(sesoi=1.5 * scale, sesoi_source="example")
    a = plan.analyze(t).evidence
    b = plan.analyze(estimate=x.mean() - popmean, se=stats.sem(x), df=99).evidence
    assert a.estimate == pytest.approx(1.2 * scale, rel=1e-9)
    assert a.p_zero == pytest.approx(t.pvalue, rel=1e-6)
    assert a.claim_class == b.claim_class == "nonzero_negligible"


def test_adapter_requires_a_reported_statistic_and_p_value():
    class NoP:
        params = np.array([1.0])
        bse = np.array([0.5])
        tvalues = np.array([2.0])
        pvalues = np.array([np.nan])
        use_t = False

    with pytest.raises(AdapterMismatch, match="finite"):
        sw.declare().analyze(NoP(), term=0)


def test_adapter_detects_a_different_statistic():
    class Wrong:
        params = np.array([1.0])
        bse = np.array([0.5])
        tvalues = np.array([3.0])
        pvalues = np.array([2 * stats.norm.sf(2.0)])
        use_t = False

    with pytest.raises(AdapterMismatch, match="statistic"):
        sw.declare().analyze(Wrong(), term=0)


# ---- P1: false "consistent" judgments --------------------------------------

@pytest.fixture
def r():
    return sw.declare(sesoi=3, sesoi_source="teachers", units="points", scope="students").analyze(
        estimate=4.2, se=1.6, df=58)


@pytest.mark.parametrize("sentence,rule,level", [
    ("The estimated effect was -4.2 points.", "reported-number", "conflict"),
    ("The data are compatible with a negative effect.", "compatible", "conflict"),
    ("The result was statistically significant (p <= 0).", "p-value", "conflict"),
    ("The result was statistically significant (p <= 0.01).", "p-value", "conflict"),
    ("The effect is positive with a confidence interval of 7.4 to 1.0.", "range", "conflict"),
    ("The 95% confidence interval ranged from -7.4 to -1.0.", "range", "conflict"),
    ("All students saw increased scores.", "generalization", "conflict"),
    ("The effect was 1.6 points.", "reported-number", "check"),
])
def test_review_sentences_no_longer_consistent(r, sentence, rule, level):
    res = r.check(sentence)
    hits = [w for w in res.warnings if w.rule == rule]
    assert hits and hits[0].status == level, str(res)


@pytest.mark.parametrize("sentence", [
    "The estimated effect was 4.2 points.",
    "The 95% confidence interval ranged from 1.0 to 7.4.",
    "The effect is positive (95% CI [0.997, 7.40]).",
    "The data are compatible with a positive effect.",
    "The result was statistically significant (p <= 0.012).",
    "The standard error was 1.6.",
    "The smallest effect size of interest was 3 points.",
])
def test_correct_versions_stay_free_of_warnings(r, sentence):
    res = r.check(sentence)
    assert res.status == "no_warnings", str(res)


def test_number_without_a_role_is_never_consistent(r):
    res = r.check("Scores went up, 4.2 in total.")
    assert any(w.rule == "unverified-number" for w in res.warnings)


def test_multi_span_parts_have_one_span_per_piece(r):
    s = "Scores increased but also decreased."
    w = r.check(s).warnings[0]
    assert [s[a:b] for a, b in w.spans] == ["increased", "decreased"]
    assert w.text == "increased … decreased"


# ---- P1: boundary, thresholds, registration --------------------------------

def test_interval_touching_the_bound_is_not_beyond_it():
    bound = float(stats.norm.isf(0.025))  # exactly the interval's end
    res = sw.declare(sesoi=bound, sesoi_source="example").analyze(estimate=0, se=1)
    assert res.evidence.claim_class == "inconclusive_at_bound"
    assert "beyond" not in res.claims.allowed[0].text
    # the review's version (ppf, which differs from isf in the last digit) reads the same
    bound2 = float(stats.norm.ppf(0.975))
    res2 = sw.declare(sesoi=bound2, sesoi_source="example").analyze(estimate=0, se=1)
    assert res2.evidence.claim_class == "inconclusive_at_bound"


def test_strictly_beyond_is_still_beyond():
    res = sw.declare(sesoi=1.9, sesoi_source="example").analyze(estimate=0, se=1)
    assert res.evidence.claim_class == "inconclusive_both"


def test_displayed_thresholds_are_conservative():
    res = sw.declare().analyze(ci=(0.9966, 4.9144))
    th = res.thresholds
    lines = " ".join(res._threshold_lines())
    shown_low = float(lines.split("below **")[1].split("**")[0])
    shown_high = float(lines.split("above **")[1].split("**")[0])
    assert shown_low <= th.met_below and shown_high >= th.equivalence_above
    for d in np.linspace(shown_low * 0.5, shown_low, 50, endpoint=False):
        assert th.decision(d) == "exceeds"
    for d in np.linspace(shown_high, shown_high * 2, 50)[1:]:
        assert th.decision(d) == "equivalent"
    assert th.decision(0.9968) == th.decision(4.912) == "undetermined"


def test_registration_is_always_reported_as_unverified():
    res = sw.declare(sesoi=3, sesoi_source="x", registration="not a registration").analyze(estimate=4.2, se=1.6, df=58)
    d = res.to_dict()
    assert d["plan"]["registration_verified"] is False
    assert any("before the data were seen" in x for x in d["not_verified"])
    md = res.to_markdown()
    assert "Declared before analysis" not in md and "timing not verified" in md and "not verified" in md


# ---- P2 ---------------------------------------------------------------------

def test_standard_policy_cites_the_interval_it_used():
    res = sw.declare(sesoi=0.2, sesoi_source="x", interval_policy="standard").analyze(estimate=0.1, se=0.058)
    w = res.check("Effects beyond the SESOI cannot be ruled out.").warnings[0]
    assert w.status == "check" and "90% CI" in w.reason and "95% CI" in w.reason


def test_near_symmetric_bounds_are_treated_as_asymmetric():
    est = -1.00000000025 - stats.norm.ppf(0.975) * 0.1
    res = sw.declare(sesoi=(-1.0000000005, 1), sesoi_source="x").analyze(estimate=est, se=0.1)
    assert res.evidence.exceeds_sesoi is False
    assert res.to_dict()["thresholds"]["declared_threshold"] is None


def test_fingerprint_versions():
    plan = sw.declare(sesoi=3, sesoi_source="t")
    assert plan.fingerprint == plan.fingerprint_for(2) != plan.fingerprint_for(1)
    assert plan.to_dict()["fingerprint_version"] == 2
    # version 1 is the 0.2.0 format: no outcome or contrast keys
    import hashlib
    v1 = {"sesoi": [-3.0, 3.0], "sesoi_source": "t", "alpha": 0.05, "interval_policy": "single",
          "units": None, "scope": None, "better": "higher"}
    blob = json.dumps(v1, sort_keys=True, separators=(",", ":"))
    assert plan.fingerprint_for(1) == hashlib.sha256(blob.encode()).hexdigest()


def test_raw_inputs_are_kept():
    res = sw.declare().analyze(estimate=4.21, ci=(1.0, 7.4), df=58)
    raw = res.to_dict()["raw_input"]
    assert raw["estimate"] == 4.21 and raw["ci"] == [1.0, 7.4] and raw["ci_level"] == 0.95
    assert res.evidence.estimate == pytest.approx(4.2)  # the midpoint is what was analysed


def test_infinite_df_is_json_safe():
    res = sw.declare().analyze(estimate=1, se=1, df=float("inf"))
    assert res.evidence.df is None
    json.loads(res.to_json())  # to_json uses allow_nan=False


def test_levels_show_the_digits_they_need():
    res = sw.declare(sesoi=1, sesoi_source="x", alpha=0.001, interval_policy="standard").analyze(estimate=0.1, se=0.1)
    md = res.to_markdown()
    assert "99.9%" in md and "99.8%" in md


def test_small_alpha_is_finite_and_tiny_alpha_refused():
    ev = sw.declare(alpha=1e-10).analyze(estimate=10, se=1).evidence
    assert all(np.isfinite(ev.zero_interval)) and ev.differs_from_zero
    with pytest.raises(ValueError):
        sw.declare(alpha=1e-16)


def test_checked_sentences_are_kept_in_the_report():
    res = sw.declare(sesoi=3, sesoi_source="t").analyze(estimate=4.2, se=1.6, df=58, label="H1")
    res.check("There is no effect.")
    res.check("Draft only.", record=False)
    d = res.to_dict()
    assert [c["sentence"] for c in d["checked_sentences"]] == ["There is no effect."]
    assert d["checked_sentences"][0]["label"] == "H1"
    assert "Sentences checked" in res.to_markdown()


def test_thresholds_match_evaluate_at_exact_cutoffs():
    th = evaluate(4.2, 1.6, 58, 0.05, "single", None).thresholds()
    for d in (th.met_below, th.equivalence_above):
        ev = evaluate(4.2, 1.6, 58, 0.05, "single", (-d, d))
        assert not ev.exceeds_sesoi and not ev.equivalent
        assert th.decision(d) == "undetermined"
