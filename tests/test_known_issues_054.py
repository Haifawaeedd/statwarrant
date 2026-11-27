"""0.5.4: two known issues from outside checks of 0.5.3.

1. A stated minimum or maximum size ("by at least 3 points") inside a comparison that
   cannot be tied to the declared contrast was only "to verify", even when the interval
   rules the size out whichever way the comparison runs. It is now a conflict.
2. Causal claims made with nouns ("causality", "causation") were not recognised.
"""

import pytest

import statwarrant as sw


PLAN = dict(sesoi=3, sesoi_source="smallest score gain teachers act on", units="points",
            scope="first-year students, one university, one term", outcome="exam performance",
            contrast="new method minus existing method")


def _res(estimate=4.27, ci=(0.40, 8.15), **extra):
    return sw.declare(**PLAN, **extra).analyze(estimate=estimate, ci=ci)


def _part(report, rule):
    found = [p for p in report.parts if p.rule == rule]
    assert found, f"no {rule} part in {report}"
    return found[0]


@pytest.mark.parametrize("sentence", [
    "The new method improved exam performance by at least 3 points.",
    "The new method improved exam performance by more than 3 points.",
    "The new method improved exam performance by over 3 points.",
    "The new method worsened exam performance by at least 3 points.",
])
def test_lower_bound_ruled_out_in_both_orders_is_conflict(sentence):
    part = _part(_res().check(sentence), "magnitude")
    assert part.status == "conflict"
    assert "whichever way the comparison runs" in part.reason


def test_lower_bound_established_is_not_a_conflict():
    report = _res(estimate=6.0, ci=(4.0, 8.0)).check(
        "The new method improved exam performance by at least 3 points.")
    assert _part(report, "magnitude").status != "conflict"


def test_negated_bound_is_not_a_conflict():
    report = _res().check("The new method did not improve exam performance by at least 3 points.")
    assert not report.conflicts


def test_other_unit_is_not_compared():
    report = _res().check("The new method improved exam performance by at least 3 percentage points.")
    assert _part(report, "magnitude").status == "check"


def test_plain_size_is_still_to_verify():
    report = _res().check("The new method improved exam performance by about 4 points.")
    assert _part(report, "magnitude").status == "check"


@pytest.mark.parametrize("sentence", [
    "The results prove causality.",
    "These data establish causation.",
    "There is a causal relationship between the method and exam performance.",
])
def test_causal_nouns_are_recognised(sentence):
    assert _part(_res().check(sentence), "causal").status == "check"


def test_causal_noun_with_observational_design_is_conflict():
    report = _res(design="observational").check("The results establish causation.")
    assert _part(report, "causal").status == "conflict"


def test_causes_of_death_still_names_an_outcome():
    report = _res().check("Causes of death were similar between groups.")
    assert not [p for p in report.parts if p.rule == "causal"]
