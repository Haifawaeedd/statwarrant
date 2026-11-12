"""Checks motivated by the external review's historical paired sleep data.

The numerical summary is for drug 2 minus drug 1, n=10, documented by R's
sleep dataset. The one-hour SESOI is illustrative, not a clinical standard.
"""
import pytest
import statwarrant as sw


@pytest.fixture
def sleep_result():
    return sw.declare(sesoi=1, sesoi_source="illustrative only", units="hours",
                      interval_policy="standard").analyze(
        estimate=1.58, se=0.3889587238883952, df=9
    )


def test_real_sleep_numerical_results(sleep_result):
    ev = sleep_result.evidence
    assert ev.p_zero == pytest.approx(0.002832890197384273, rel=1e-12)
    assert ev.p_equivalence == pytest.approx(0.9149441145512887, rel=1e-12)
    assert ev.differs_from_zero
    assert not ev.equivalent and not ev.exceeds_sesoi


@pytest.mark.parametrize("sentence", [
    "The equivalence test gave p < 0.05.",
    "The equivalence test was statistically significant.",
])
def test_equivalence_test_not_confused_with_zero_test(sleep_result, sentence):
    checked = sleep_result.check(sentence, record=False)
    assert checked.level in ("check", "conflict")
    assert checked.status == "warnings"
    assert not any(part.status == "consistent" for part in checked.parts)


def test_zero_test_significance_is_not_equivalence(sleep_result):
    checked = sleep_result.check("The difference was statistically significant.", record=False)
    assert not any(part.status == "conflict" for part in checked.parts)
