"""0.6.1: wordings from an outside real-data benchmark (InsectSprays and others, Welch contrasts)."""
import pytest

import statwarrant as sw


def res(estimate, ci, sesoi):
    return sw.declare(sesoi=sesoi, sesoi_source="illustrative", contrast="A minus C", outcome="count").analyze(
        estimate=estimate, ci=ci, df=20)


BIG = dict(estimate=12.42, ci=(9.26, 15.57), sesoi=3)      # beyond the SESOI
EQUIV = dict(estimate=1.0, ci=(-2, 4), sesoi=30)           # equivalent
INCONCL = dict(estimate=1.0, ci=(-2, 4), sesoi=3)          # inconclusive

BEYOND = ["The population effect is beyond the range deemed negligible.",
          "The effect lies outside the region of negligible differences.",
          "The effect is outside the negligible range."]


@pytest.mark.parametrize("text", BEYOND)
def test_beyond_negligible_is_an_importance_claim(text):
    assert res(**BIG).check(text, record=False).level != "conflict"
    assert res(**EQUIV).check(text, record=False).level == "conflict"
    assert res(**INCONCL).check(text, record=False).level == "conflict"


def test_negligible_alone_is_still_a_smallness_claim():
    assert res(**BIG).check("The effect was negligible.", record=False).level == "conflict"


@pytest.mark.parametrize("text", ["A and B have the same population mean.", "The means were identical."])
@pytest.mark.parametrize("case", [BIG, EQUIV, INCONCL])
def test_identical_means_is_a_no_effect_claim(text, case):
    assert res(**case).check(text, record=False).level == "conflict"
