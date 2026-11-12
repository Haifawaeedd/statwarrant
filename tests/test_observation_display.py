"""Regressions for misleading output exposed by real-data validation."""
import json
import math

import pytest

import statwarrant as sw
from statwarrant.claims import fmt_interval


def test_norris_interval_is_not_displayed_as_a_point():
    # NIST Norris certified slope and SE, with df=34.
    result = sw.declare(sesoi=0.1, sesoi_source="illustrative").analyze(
        estimate=1.00211681802045, se=0.000429796848199937, df=34
    )
    ci = result.context.ci_text()
    assert ci == "95% CI [1.001, 1.003] (endpoints rounded for display)"
    assert "95% [1.001, 1.003]" in result.to_markdown()
    assert "[1, 1]" not in str(result.check("The slope was negative.", record=False))


@pytest.mark.parametrize("lo,hi", [
    (1.0012433657, 1.0029902703),
    (-1.0029902703, -1.0012433657),
    (1.0, math.nextafter(1.0, math.inf)),
    (math.nextafter(0.0, math.inf), math.nextafter(math.nextafter(0.0, math.inf), math.inf)),
])
def test_distinct_binary64_endpoints_do_not_collapse_when_printed(lo, hi):
    formatted = fmt_interval(lo, hi)
    a, b = map(float, formatted.strip("[]").split(", "))
    assert a < b


def test_unsupported_sentence_is_in_unchecked_json_and_markdown():
    result = sw.declare().analyze(estimate=1, se=0.2)
    sentence = "The instrument is safe and reliable."
    check = result.check(sentence)
    assert check.status == "no_supported_pattern"
    assert check.unchecked == (sentence,)
    assert check.to_dict()["unchecked"] == [sentence]
    assert sentence in result.to_markdown()
    assert sentence in json.loads(result.to_json())["checked_sentences"][0]["unchecked"]


def test_ambiguous_numbers_are_not_claimed_equal_merely_by_rounding():
    result = sw.declare(sesoi=0.5, sesoi_source="illustrative").analyze(estimate=-0.371, se=0.311, df=16.5)
    check = result.check("Treatment 1 improved health.", record=False)
    for warning in check.warnings:
        if warning.rule == "unverified-number":
            assert "equals the" not in warning.reason
            assert "after rounding" in warning.reason or "matches nothing" in warning.reason


def test_threshold_text_uses_zero_test_not_rounded_interval_claim():
    result = sw.declare().analyze(estimate=127.73562964352773, se=65.17243717287157)
    assert not result.evidence.differs_from_zero
    assert result.evidence.zero_interval[0] > 0  # floating-point boundary case
    line = result._threshold_lines()[0]
    assert "difference from zero is not established" in line
    assert "includes zero" not in line
