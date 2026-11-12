"""'Neither X nor Y was established' is judged item by item, not read as 'no effect'.

The second user trial found false conflicts on correct sentences of this form. The
sentences here come from that trial (now development data) and variants of them; none
comes from the third trial's frozen evaluation set.
"""

import math

import pytest

import statwarrant as sw

# second-trial result: diabetes progression, sex group 2 minus group 1 (inconclusive)
DIA = sw.declare(sesoi=15.418600906598218, sesoi_source="trial", units="progression units",
                 outcome="disease progression after one year").analyze(
    estimate=6.645390070921962, se=7.350162171329782, df=440)
# second-trial result: PSI teaching method, log-odds (significant, size undetermined)
PSI = sw.declare(sesoi=math.log(1.68), sesoi_source="trial", units="log-odds").analyze(
    estimate=2.3786876550933544, se=1.0645642544971325)
EQUIV = sw.declare(sesoi=0.02, sesoi_source="test", units="accuracy").analyze(estimate=0.001, se=0.003, df=500)
NO_SESOI = sw.declare(units="points").analyze(estimate=1.0, se=2.0, df=50)


@pytest.mark.parametrize("res,sentence,level", [
    (DIA, "Neither a difference from zero nor equivalence was established.", None),
    (DIA, "Neither equivalence nor a difference from zero could be established.", None),
    (DIA, "The data support neither a positive nor a negative effect.", None),
    (DIA, "There was neither a significant difference nor equivalence.", None),
    (PSI, "Neither a difference from zero nor equivalence was established.", "conflict"),   # significant
    (PSI, "Neither an increase nor a decrease was established.", "conflict"),               # a direction is
    (EQUIV, "Neither a difference from zero nor equivalence was shown.", "conflict"),       # equivalent
    (NO_SESOI, "Neither a difference from zero nor equivalence was established.", "check"),  # not tested
])
def test_neither_nor_is_judged_item_by_item(res, sentence, level):
    out = res.check(sentence, record=False)
    assert out.level == level, str(out)
    assert "no-effect" not in [p.rule for p in out.parts]


def test_neither_equivalence_nor_a_larger_effect_is_a_check_not_a_conflict():
    # The branch's conservative rule covers this construction; the size qualifier on
    # "an effect" must not be judged on its own as a claim of importance.
    out = DIA.check("The result supports neither equivalence nor an effect larger than the smallest effect size "
                    "of interest.", record=False)
    assert out.level == "check", str(out)
    assert "importance" not in [p.rule for p in out.parts]


def test_item_with_its_own_threshold_is_a_check():
    out = DIA.check("Neither a difference from zero nor an effect larger than 20 units was established.", record=False)
    assert out.level == "check" and "own threshold" in out.warnings[0].reason, str(out)


def test_bare_neither_equivalence_nor_an_effect_stays_a_check():
    # Without "established", "supports" or similar, the branch's conservative rule is kept.
    out = DIA.check("There was neither equivalence nor an effect.", record=False)
    assert out.level == "check" and "neither-equivalence" in [p.rule for p in out.parts], str(out)


def test_neither_nor_without_established_is_still_a_claim_of_no_effect():
    out = DIA.check("Scores neither improved nor declined.", record=False)
    assert out.level is not None
