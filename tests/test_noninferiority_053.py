"""0.5.3: a test statwarrant does not run is never judged against, or replaced by, the zero test.

Figures from PREVENT CLOT (O'Toole et al., NEJM 2023): death at 90 days 0.78% with aspirin and
0.73% with low-molecular-weight heparin; difference 0.05 percentage points, 96.2% CI -0.27 to
0.38; non-inferiority margin 0.75 points; P<0.001 for non-inferiority. The zero test of the same
difference gives p of about 0.75.
"""
import pytest
from scipy.stats import norm

import statwarrant as sw

SE = (0.38 + 0.27) / (2 * norm.ppf(1 - (1 - 0.962) / 2))


@pytest.fixture
def clot():
    return sw.declare(sesoi=0.75, sesoi_source="trial non-inferiority margin", units="percentage points",
                      better="lower", outcome="death at 90 days",
                      contrast="aspirin minus low-molecular-weight heparin").analyze(estimate=0.05, se=SE)


def statuses(out, rule):
    return [p.status for p in out.parts if p.rule == rule]


@pytest.mark.parametrize("text", [
    "Aspirin was noninferior to low-molecular-weight heparin in preventing death (P<0.001 for noninferiority).",
    "Aspirin was noninferior to low-molecular-weight heparin (P<0.001).",
    "The noninferiority test was significant (p < 0.001).",
    "Aspirin was non-inferior to heparin with respect to death at 90 days.",
    "Death occurred in 0.78% of the aspirin group and 0.73% of the heparin group (difference, 0.05 percentage "
    "points; 96.2% CI, -0.27 to 0.38; P<0.001 for noninferiority).",
])
def test_noninferiority_claims_are_sent_to_review_not_judged_by_the_zero_test(clot, text):
    out = clot.check(text, record=False)
    assert "conflict" not in statuses(out, "p-value") + statuses(out, "significance")
    assert "consistent" not in statuses(out, "p-value") + statuses(out, "significance")
    assert not any("Copy the p-value" in p.action for p in out.parts)


def test_noninferiority_is_named_as_unchecked(clot):
    out = clot.check("Aspirin was noninferior to low-molecular-weight heparin.", record=False)
    assert statuses(out, "noninferiority") == ["check"]
    assert statuses(out, "direction") == []  # "non-inferior" is not the direction word "inferior"


def test_superiority_test_is_another_test(clot):
    out = clot.check("The superiority test was not significant (p = 0.75).", record=False)
    assert "conflict" not in [p.status for p in out.parts]


def test_an_explicit_zero_test_claim_is_still_judged(clot):
    out = clot.check("Aspirin was noninferior; the zero test gave p < 0.001.", record=False)
    assert statuses(out, "p-value") == ["conflict"]
    out = clot.check("There was a significant difference in death (p < 0.001).", record=False)
    assert "conflict" in statuses(out, "significance")
