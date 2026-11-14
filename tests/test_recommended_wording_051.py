"""0.5.1: wording statwarrant itself recommends must not be a conflict.

Found by the 'which result?' reader experiment (14 Nov 2026): 15 of 190 correctly worded
sentences got a false conflict because "matter", "no effect" and "meaningful" were read
without the words around them. Each case is checked against all four result types, so the
same wording still conflicts with a result it does not describe.
"""

import pytest

import statwarrant as sw


def _result(estimate, se):
    return sw.declare(sesoi=3, sesoi_source="test", units="points", outcome="exam scores",
                      contrast="the new teaching method minus the standard method",
                      better="higher").analyze(estimate=estimate, se=se)


RESULTS = {"inconclusive": _result(1.8, 1.8), "too small": _result(1.0, 0.36), "large": _result(6.6, 1.05),
           "equivalent": _result(0.3, 0.9)}
CASES = [
    ("The effect was real but too small to matter.", {"too small", "equivalent"}),
    ("The difference was too small to be practically important.", {"too small", "equivalent"}),
    ("The data are compatible with no effect and with an effect larger than 3 points.", {"inconclusive"}),
    ("The data are compatible with no effect.", {"inconclusive", "equivalent"}),
    ("The data neither show an effect of the new teaching method nor rule out a meaningful one.", {"inconclusive"}),
    ("The results neither demonstrate a difference nor rule out an important one.", {"inconclusive"}),
]


@pytest.mark.parametrize("sentence, fits", CASES)
@pytest.mark.parametrize("kind", list(RESULTS))
def test_recommended_wording(sentence, fits, kind):
    out = RESULTS[kind].check(sentence, record=False)
    if kind in fits:
        assert out.level != "conflict", str(out)
    else:
        assert out.level == "conflict", str(out)


def test_claims_of_importance_and_no_effect_are_still_read():
    inc = RESULTS["inconclusive"]
    assert inc.check("The effect was large enough to matter.", record=False).level == "conflict"
    assert inc.check("There was no effect.", record=False).level == "conflict"
    assert inc.check("The new teaching method had no effect, so it does not matter.", record=False).level == "conflict"
