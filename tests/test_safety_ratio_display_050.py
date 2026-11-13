"""Ratio-scale notes must not lose the null, ordering or finite-range safety."""

import json
import math
import re
from decimal import Decimal, localcontext

import pytest

import statwarrant as sw
from statwarrant._ratio_display import ratio_scale_note


NOTE = re.compile(
    r"^On the ratio scale: (.+?) \(([^ ]+) CI (.+?) to (.+?)\), "
    r"a relative change of (.+?)% \((.+?)% to (.+?)%\)\."
)


def _note(result):
    (note,) = [n for n in result.claims.notes if n.startswith("On the ratio scale")]
    assert note in result.raw_input["provenance_notes"]
    return note


def _ratio_decimal(text):
    with localcontext() as ctx:
        ctx.prec = 350
        if " + " in text:
            left, right = text.split(" + ")
            return Decimal(left) + Decimal(right)
        if " - " in text:
            left, right = text.split(" - ")
            return Decimal(left) - Decimal(right)
        return Decimal(text)


def _summary(note):
    match = NOTE.match(note)
    assert match, note
    mid, level, lo, hi, mid_pct, lo_pct, hi_pct = match.groups()
    return level, tuple(map(_ratio_decimal, (mid, lo, hi))), tuple(
        Decimal(x) for x in (mid_pct, lo_pct, hi_pct)
    )


def _assert_order_and_null(result):
    level, ratios, percents = _summary(_note(result))
    logs = (result.evidence.estimate, *result.evidence.zero_interval)
    for log_value, ratio, percent in zip(logs, ratios, percents):
        assert (ratio > 1) == (log_value > 0)
        assert (ratio < 1) == (log_value < 0)
        assert (percent > 0) == (log_value > 0)
        assert (percent < 0) == (log_value < 0)
        assert ratio > 0 and percent > -100
        with localcontext() as ctx:
            ctx.prec = 350
            implied_percent = (ratio - 1) * 100
            assert abs(implied_percent - percent) <= Decimal("0.015") * max(
                abs(implied_percent), abs(percent)
            )
    for i in range(3):
        for j in range(i):
            assert (ratios[i] < ratios[j]) == (logs[i] < logs[j])
            assert (ratios[i] > ratios[j]) == (logs[i] > logs[j])
            assert (percents[i] < percents[j]) == (logs[i] < logs[j])
            assert (percents[i] > percents[j]) == (logs[i] > logs[j])
    assert json.loads(result.to_json(allow_nan=False))["evidence"]["estimate"] == logs[0]
    return level, ratios, percents


def test_published_ratio_uses_reconstructed_midpoint_and_correct_quantity():
    result = sw.declare(units="log odds ratio").analyze(
        estimate=0.83, ci=(0.75, 0.93), ratio=True
    )
    note = _note(result)
    assert "0.8352 (95% CI 0.75 to 0.93)" in note
    assert "-16.5% (-25.0% to -7.0%)" in note
    assert "reconstructed from the input interval" in note
    assert "odds rather than risk" in note
    assert "comparison order is as supplied" in note
    _assert_order_and_null(result)


@pytest.mark.parametrize("ci", [
    (1.00002, 1.00018),
    (0.9998, 0.99998),
    (0.99995, 1.00006),
    (math.nextafter(1.0, 0.0), math.nextafter(1.0, 2.0)),
    (1.0, math.nextafter(1.0, 2.0)),
    (math.nextafter(1.0, 0.0), 1.0),
])
def test_near_one_preserves_all_signs_and_interval_order(ci):
    result = sw.declare(units="log risk ratio").analyze(ci=ci, ratio=True)
    assert _assert_order_and_null(result)[0] == "95%"


def test_review_near_one_values_are_not_all_rounded_to_the_null():
    result = sw.declare(units="log risk ratio").analyze(
        estimate=1.0001, ci=(1.00002, 1.00018), ratio=True
    )
    _, ratios, percents = _assert_order_and_null(result)
    assert ratios == (Decimal("1.0001"), Decimal("1.00002"), Decimal("1.00018"))
    assert percents[0] == pytest.approx(Decimal("0.01"), rel=Decimal("0.001"))
    assert percents[1] > 0 and percents[2] > percents[0]


def test_expm1_retains_change_even_when_exp_rounds_to_one():
    result = sw.declare().analyze(
        ci=(math.nextafter(1.0, 0.0), math.nextafter(1.0, 2.0)), ratio=True
    )
    assert math.exp(result.evidence.estimate) == 1.0
    note = _note(result)
    assert "1 + " in note
    _, ratios, percents = _assert_order_and_null(result)
    assert ratios[0] > 1 and percents[0] > 0
    assert float(percents[0]) == pytest.approx(
        100 * math.expm1(result.evidence.estimate), rel=0.001
    )


def test_smallest_subnormal_log_changes_are_not_printed_as_zero_or_one():
    tiny = math.nextafter(0.0, 1.0)
    note = ratio_scale_note(-tiny, (-2 * tiny, 0.0), 0.95)
    _, ratios, percents = _summary(note)
    assert ratios[1] < ratios[0] < 1 == ratios[2]
    assert percents[1] < percents[0] < 0 == percents[2]


@pytest.mark.parametrize("ci, ci_level, alpha", [
    ((1e-250, 1e250), 0.8, 0.05),  # exp overflows and underflows
    ((1e-201, 1e201), 0.8, 0.05),  # exp fits, percentage overflows
    ((1e-202, 1e202), 0.8, 0.05),
    ((0.01, 100), 0.01, 0.05),
    ((1.0, 1e307), 0.95, 0.05),  # percentage overflows although ratio fits
    ((1e-300, 1e-250), 0.8, 0.05),  # ratio underflows at the lower end
    ((1e-250, 1e250), 0.8, 0.2),  # input/output levels match, no exp overflow
])
def test_extreme_intervals_retain_finite_log_evidence_and_strict_json(ci, ci_level, alpha):
    result = sw.declare(alpha=alpha, units="log risk ratio").analyze(
        ci=ci, ci_level=ci_level, ratio=True
    )
    note = _note(result)
    assert "summary is omitted" in note
    assert "log scale in evidence" in note and "expm1(x)" in note
    assert "inf%" not in note.lower() and "nan%" not in note.lower()
    assert all(math.isfinite(x) for x in (result.evidence.estimate, *result.evidence.zero_interval))
    raw = result.to_json(allow_nan=False)
    decoded = json.loads(raw, parse_constant=lambda value: pytest.fail(f"non-finite JSON: {value}"))
    assert decoded["evidence"]["zero_test"]["interval"] == list(result.evidence.zero_interval)
    assert note in str(result)


@pytest.mark.parametrize("lo, hi", [(-746.0, -740.0), (0.0, 710.0), (0.0, 706.0), (-40.0, 0.0)])
def test_float_boundary_failures_omit_the_summary_instead_of_losing_information(lo, hi):
    note = ratio_scale_note((lo + hi) / 2, (lo, hi), 0.95)
    assert "summary is omitted" in note
    assert "inf%" not in note.lower()


def test_percent_very_close_to_minus_100_is_not_shown_as_exactly_minus_100():
    note = ratio_scale_note(-18.5, (-37.0, 0.0), 0.95)
    _, _, percents = _summary(note)
    assert Decimal(-100) < percents[1] < percents[0] < 0


@pytest.mark.parametrize("alpha, level_text", [(0.05, "95%"), (0.1, "90%")])
def test_ratio_interval_uses_output_confidence_level_not_input_level(alpha, level_text):
    result = sw.declare(alpha=alpha).analyze(
        estimate=0.83, ci=(0.75, 0.93), ci_level=0.9, ratio=True
    )
    level, ratios, _ = _assert_order_and_null(result)
    assert level == level_text
    if alpha == 0.1:
        assert float(ratios[1]) == pytest.approx(0.75, rel=0.0001)
        assert float(ratios[2]) == pytest.approx(0.93, rel=0.0001)
    else:
        assert float(ratios[1]) < 0.75
        assert float(ratios[2]) > 0.93


def test_wide_but_representable_interval_remains_useful():
    result = sw.declare(alpha=0.2).analyze(ci=(0.01, 100.0), ci_level=0.8, ratio=True)
    level, ratios, _ = _assert_order_and_null(result)
    assert level == "80%"
    assert float(ratios[1]) == pytest.approx(0.01, rel=0.001)
    assert float(ratios[2]) == pytest.approx(100, rel=0.001)
