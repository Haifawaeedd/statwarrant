"""Warning messages say what was not checked (review of the third user trial).

Reproduces a review finding: a percentage inside an unbound comparison was reported with
the generic direction message, which did not explain the numeric check.
"""

import statwarrant as sw

DIRECTION_TEXT = "The direction's relationship to the declared contrast"


def _part(out, rule):
    return next(p for p in out.parts if p.rule == rule)


def test_percentage_in_unbound_comparison_has_its_own_reason():
    res = sw.declare(sesoi=0.1, sesoi_source="test", units="log rate ratio",
                     contrast="per unit of dose").analyze(estimate=-0.05, se=0.01)
    out = res.check("Each extra unit of dose lowered the event rate by about 5%.", record=False)
    pct = _part(out, "percentage")
    assert pct.status == "check"
    assert "this percentage" in pct.reason and DIRECTION_TEXT not in pct.reason
    assert "absolute (percentage points) or relative" in pct.reason
    assert DIRECTION_TEXT in _part(out, "direction").reason


def test_size_in_unbound_comparison_names_the_size():
    res = sw.declare(sesoi=2, sesoi_source="test", units="points",
                     contrast="new minus old").analyze(estimate=3.0, se=1.0, df=40)
    out = res.check("Scores under the old method were 3 points lower than under the new method.", record=False)
    size = _part(out, "magnitude")
    assert size.status == "check" and "this size" in size.reason and "new minus old" in size.reason
