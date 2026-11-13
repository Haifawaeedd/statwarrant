"""SESOI display must describe the actual binary64 decision, not a rounded neighbour."""
import json
import math
import random
import re
import struct
import sys

import pytest

import statwarrant as sw
from statwarrant.claims import fmt_bound, fmt_bounds, fmt_ci


def _bits(x):
    return struct.pack(">d", x)


def _reported_bounds(result):
    line = next(line for line in result.to_markdown().splitlines()
                if "**Smallest effect size of interest:**" in line)
    match = re.search(r"\[([^,]+), ([^\]]+)\]", line)
    assert match is not None
    return tuple(float(part) for part in match.groups())


def _part(result, sentence, rule):
    return next(part for part in result.check(sentence, record=False).parts if part.rule == rule)


def test_reported_decision_uses_the_declared_threshold_not_a_rounded_neighbour():
    result = sw.declare(sesoi=1.0024, sesoi_source="x").analyze(estimate=1.002396, se=0.0001)
    assert result.thresholds.decision(1.0) == "exceeds"
    assert result.thresholds.decision(1.0024) == "undetermined"
    assert not result.evidence.exceeds_sesoi
    assert not result.evidence.equivalent
    assert _reported_bounds(result) == (-1.0024, 1.0024)
    assert "Your declared threshold (±1.0024): neither is established" in result.to_markdown()
    assert "smallest effect size of interest (1.0024)" in str(result)
    assert json.loads(result.to_json())["thresholds"]["declared_threshold"] == "undetermined"


@pytest.mark.parametrize("d", [
    3.0,
    1.0024,
    math.nextafter(1.0024, math.inf),
    math.nextafter(1.0, math.inf),
    math.nextafter(0.0, math.inf),
    math.nextafter(1e-300, math.inf),
    math.nextafter(1e300, math.inf),
    sys.float_info.max,
])
def test_symmetric_thresholds_round_trip_over_the_float_domain(d):
    se = min(max(d, 1e-300), 1e307)
    result = sw.declare(sesoi=d, sesoi_source="x").analyze(estimate=0, se=se)
    lo, hi = _reported_bounds(result)
    assert _bits(lo) == _bits(-d)
    assert _bits(hi) == _bits(d)
    line = next(line for line in result._threshold_lines() if "Your declared threshold" in line)
    token = re.search(r"threshold \(±([^)]*)\)", line).group(1)
    assert _bits(float(token)) == _bits(d)
    assert result.thresholds.decision(float(token)) == result.thresholds.decision(d)


def test_round_trip_formatter_for_random_finite_binary64_bounds():
    rng = random.Random(947)
    for _ in range(2000):
        bits = rng.randrange(1, 0x7ff0000000000000)
        x = struct.unpack(">d", struct.pack(">Q", bits))[0]
        assert _bits(float(fmt_bound(x))) == _bits(x)
        assert _bits(float(fmt_bound(-x))) == _bits(-x)


def test_asymmetric_nearby_bounds_are_not_printed_as_symmetric():
    bounds = (-1.0000000005, 1.0)
    result = sw.declare(sesoi=bounds, sesoi_source="x").analyze(estimate=0, se=0.1)
    assert _reported_bounds(result) == bounds
    assert "[-1.0000000005, 1]" in result.to_markdown()
    assert "[-1.0000000005, 1]" in result.claims.allowed[0].text
    assert "declared bounds are asymmetric" in result.to_markdown()
    assert result.to_dict()["thresholds"]["declared_threshold"] is None
    for sentence, rule in [("The SESOI bounds are [-2, 2].", "range"),
                           ("The smallest effect size of interest is 2.", "reported-number"),
                           ("The effect is important.", "importance"),
                           ("The conditions are equivalent.", "equivalence")]:
        assert "[-1.0000000005, 1]" in _part(result, sentence, rule).reason


@pytest.mark.parametrize("estimate", [1.002396, -1.002396, 1.05, -1.05])
def test_positive_and_negative_claims_show_the_unrounded_bound(estimate):
    result = sw.declare(sesoi=1.0024, sesoi_source="x", units="points").analyze(
        estimate=estimate, se=0.0001
    )
    expected = "1.0024 points" if estimate > 0 else "-1.0024 points"
    assert expected in result.claims.allowed[0].text
    assert expected in str(result)
    assert expected in result.to_markdown()


def test_equivalence_claim_and_linter_reasons_display_exact_bounds():
    result = sw.declare(sesoi=1.0024, sesoi_source="x").analyze(estimate=0, se=0.1)
    bounds = "[-1.0024, 1.0024]"
    assert result.evidence.equivalent
    assert bounds in result.claims.allowed[0].text
    assert bounds in _part(result, "The conditions are equivalent.", "equivalence").reason
    assert bounds in _part(result, "There is no effect.", "no-effect").reason
    assert bounds in _part(result, "The effect is important.", "importance").reason
    assert bounds in _part(result, "The SESOI bounds are [-2, 2].", "range").reason
    assert bounds in _part(result, "The smallest effect size of interest is 2.", "reported-number").reason


def test_level_conflict_note_uses_declared_bounds():
    result = sw.declare(sesoi=1.0024, sesoi_source="x", interval_policy="standard").analyze(
        estimate=0.5012, se=0.280672
    )
    assert result.evidence.level_conflict
    note = next(note for note in result.claims.notes if "Level conflict" in note)
    assert "[-1.0024, 1.0024]" in note
    assert note in result.to_markdown()


def test_ordinary_whole_number_bounds_remain_readable():
    result = sw.declare(sesoi=3, sesoi_source="x", units="points").analyze(estimate=4.2, se=1.6, df=58)
    assert "[-3, 3]" in result.to_markdown()
    assert "Your declared threshold (±3 points)" in result.to_markdown()
    assert fmt_bound(3.0) == "3"
    assert fmt_bounds(-3.0, 3.0) == "[-3, 3]"


def test_scientific_notation_of_declared_bounds_is_read_as_one_number():
    result = sw.declare(sesoi=1e300, sesoi_source="x").analyze(estimate=0, se=1e300)
    check = result.check(f"The SESOI bounds are {fmt_bounds(*result.plan.sesoi)}.", record=False)
    assert _part(result, check.sentence, "range").status == "consistent"
    assert not any(part.rule == "unverified-number" for part in check.parts)
    assert result.check(result.claims.allowed[0].text, record=False).status == "no_warnings"


def test_ci_endpoints_are_readable_and_explicitly_marked_as_rounded():
    result = sw.declare(sesoi=0.1, sesoi_source="x").analyze(
        estimate=1.00211681802045, se=0.000429796848199937, df=34
    )
    assert "[1.001, 1.003] (endpoints rounded for display)" in result.context.ci_text()
    assert "[1.001, 1.003] (endpoints rounded for display)" in result.to_markdown()
    reason = _part(result, "The 95% CI was [2, 3].", "range").reason
    assert "[1.001, 1.003] (endpoints rounded for display)" in reason


@pytest.mark.parametrize("policy", ["single", "standard"])
def test_machine_collapsed_intervals_are_not_reported_as_exact_points(policy):
    result = sw.declare(sesoi=1.0024, sesoi_source="x", interval_policy=policy).analyze(
        estimate=1.0024, se=1e-20
    )
    assert result.evidence.zero_interval[0] == result.evidence.zero_interval[1]
    assert result.evidence.equivalence_interval[0] == result.evidence.equivalence_interval[1]
    assert result.thresholds.decision(1.0024) == "undetermined"
    caveat = "computed endpoints coincide at machine precision"
    for text in [result.context.ci_text(), result.claims.allowed[0].text,
                 str(result), result.to_markdown(),
                 _part(result, "The conditions are equivalent.", "equivalence").reason,
                 _part(result, "The 95% CI was [2, 3].", "range").reason]:
        assert caveat in text
        assert "interval width is unresolved" in text
        assert "endpoints rounded for display" in text
    assert "not established by the equivalence test" in _part(
        result, "The conditions are equivalent.", "equivalence"
    ).reason
    assert result.check(result.claims.allowed[0].text, record=False).status == "no_warnings"


def test_standard_policy_warns_when_only_equivalence_interval_collapses():
    result = sw.declare(sesoi=1, sesoi_source="x", interval_policy="standard").analyze(
        estimate=1, se=3e-17
    )
    assert result.evidence.zero_interval[0] < result.evidence.zero_interval[1]
    assert result.evidence.equivalence_interval[0] == result.evidence.equivalence_interval[1]
    assert "coincide at machine precision" not in result.context.ci_text()
    assert "coincide at machine precision" in result.context.ci_text("equivalence")
    assert "coincide at machine precision" in _part(result, "The conditions are equivalent.", "equivalence").reason
    rows = result.to_markdown().splitlines()
    eq_row = next(row for row in rows if row.startswith("| Equivalent (TOST)"))
    zero_row = next(row for row in rows if row.startswith("| Differs from zero"))
    assert "coincide at machine precision" in eq_row
    assert "coincide at machine precision" not in zero_row


def test_collapsed_zero_interval_without_a_declared_sesoi_gets_a_caveat():
    result = sw.declare().analyze(estimate=1, se=1e-20)
    assert result.evidence.zero_interval == (1.0, 1.0)
    assert "interval width is unresolved" in result.to_markdown()
    assert "interval width is unresolved" in result.claims.allowed[0].text
    assert "interval width is unresolved" in _part(result, "The effect was negative.", "direction").reason
    assert "interval width is unresolved" in fmt_ci(*result.evidence.zero_interval)
    assert result.check(result.claims.allowed[0].text, record=False).status == "no_warnings"
