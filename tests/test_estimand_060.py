"""SciPy t-test results do not record trimming: the estimand must be stated, not guessed."""

import numpy as np
import pytest
from scipy import stats

import statwarrant as sw


def _data():
    rng = np.random.default_rng(1)
    return rng.normal(5, 2, 30), rng.normal(4, 3, 25)


def _plan():
    return sw.declare(sesoi=1, sesoi_source="test", units="points", outcome="score", contrast="a minus b")


def test_trimmed_result_is_a_trimmed_mean_difference_and_the_report_warns():
    a, b = _data()
    res = _plan().analyze(stats.ttest_ind(a, b, trim=0.2))
    trimmed = stats.trim_mean(a, 0.2) - stats.trim_mean(b, 0.2)
    assert res.evidence.estimate == pytest.approx(trimmed, rel=1e-12)
    assert abs(res.evidence.estimate - (a.mean() - b.mean())) > 0.1
    note = " ".join(res.claims.notes)
    assert "trimmed means" in note and "estimand=" in note
    assert "trimmed means" in res.to_markdown()


def test_declared_estimand_is_reported_and_replaces_the_warning():
    a, b = _data()
    res = _plan().analyze(stats.ttest_ind(a, b, trim=0.2), estimand="difference in 20% trimmed means")
    assert res.estimand == "difference in 20% trimmed means"
    assert res.to_dict()["estimand"] == "difference in 20% trimmed means"
    assert "**Estimand:** difference in 20% trimmed means" in res.to_markdown()
    assert not any("does not record which variant" in n for n in res.claims.notes)


def test_estimand_without_scipy_and_empty_estimand():
    res = _plan().analyze(estimate=1.2, se=0.5, df=40, estimand="mean difference")
    assert res.to_dict()["estimand"] == "mean difference"
    assert not any("does not record which variant" in n for n in res.claims.notes)
    with pytest.raises(ValueError):
        _plan().analyze(estimate=1.2, se=0.5, estimand="  ")
