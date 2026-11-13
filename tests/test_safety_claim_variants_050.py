"""Narrow regressions for two claim-linter variants in the 0.5.0 review."""

import pytest

import statwarrant as sw


@pytest.fixture
def sleep():
    return sw.declare(sesoi=1, sesoi_source="illustration", units="hours", outcome="sleep duration").analyze(
        estimate=1.58, se=0.3889587238883952, df=9
    )


@pytest.fixture
def inconclusive():
    return sw.declare(sesoi=1, sesoi_source="illustration", units="points").analyze(estimate=0.1, se=1)


def _parts(result, sentence):
    return result.check(sentence, record=False).parts


def _part(parts, rule):
    return next(p for p in parts if p.rule == rule)


@pytest.mark.parametrize("sentence, expected", [
    ("The p-value difference was 0.00283.", "p-value difference was 0.00283"),
    ("The p value difference is 0.00283.", "p value difference is 0.00283"),
    ("The p-values difference = 0.00283.", "p-values difference = 0.00283"),
])
def test_p_difference_number_is_reviewed_not_compared_to_effect_ci(sleep, sentence, expected):
    out = sleep.check(sentence, record=False)
    part = _part(out.parts, "p-difference")
    assert part.status == "check" and part.text == expected
    assert out.level == "check", str(out)
    assert not any(p.rule in {"reported-number", "p-value"} for p in out.parts), str(out)
    assert not out.conflicts


@pytest.mark.parametrize("effect, expected", [("1.58", "consistent"), ("10", "conflict")])
def test_p_difference_does_not_mask_independent_effect_number(sleep, effect, expected):
    sentence = f"The p-value difference was 0.00283, and the effect was {effect} hours."
    out = sleep.check(sentence, record=False)
    assert _part(out.parts, "p-difference").text == "p-value difference was 0.00283"
    number = _part(out.parts, "reported-number")
    assert number.text.startswith(effect) and number.status == expected, str(out)
    assert not any(p.status == "conflict" and "0.00283" in p.text for p in out.parts), str(out)


def test_plain_p_values_and_effect_difference_still_compared(sleep):
    good = _parts(sleep, "p = 0.00283.")
    bad = _parts(sleep, "p = 0.5.")
    effect = _parts(sleep, "The effect difference was 0.00283.")
    assert _part(good, "p-value").status == "consistent"
    assert _part(bad, "p-value").status == "conflict"
    assert _part(effect, "reported-number").status == "conflict"
    assert not any(p.rule == "p-difference" for p in good + bad + effect)


def test_p_values_differed_does_not_consume_following_effect(sleep):
    out = sleep.check("The p-values differed, and the effect was 10 hours.", record=False)
    assert _part(out.parts, "p-difference").text == "p-values differed"
    assert _part(out.parts, "reported-number").status == "conflict"


@pytest.mark.parametrize("separator", ["—", " — ", " - "])
def test_independent_claims_after_dash_are_not_consumed(inconclusive, separator):
    first = "neither equivalence nor an effect larger than the SESOI"
    sentence = "The data support " + first + separator + "definitely everyone benefits."
    out = inconclusive.check(sentence, record=False)
    assert _part(out.parts, "neither-equivalence").text == first
    assert _part(out.parts, "neither-equivalence").status == "check"
    assert _part(out.parts, "certainty").text == "definitely"
    assert _part(out.parts, "certainty").status == "conflict"
    assert _part(out.parts, "generalization").text == "everyone"
    assert _part(out.parts, "generalization").status == "conflict"


def test_other_neither_pattern_also_stops_at_dash(inconclusive):
    sentence = "The data support neither a positive nor a negative effect—definitely everyone benefits."
    out = inconclusive.check(sentence, record=False)
    neither = _part(out.parts, "neither-established")
    assert neither.text == "support neither a positive nor a negative effect"
    assert _part(out.parts, "certainty").status == "conflict"
    assert _part(out.parts, "generalization").status == "conflict"


def test_caution_in_first_clause_does_not_hide_certainty_after_dash(inconclusive):
    sentence = ("The data do not prove either possibility: neither equivalence nor an effect larger than the SESOI"
                "—definitely everyone benefits.")
    out = inconclusive.check(sentence, record=False)
    assert _part(out.parts, "certainty").status == "conflict", str(out)
    assert _part(out.parts, "generalization").status == "conflict", str(out)


def test_dash_suffix_not_recognized_by_rules_remains_unchecked(inconclusive):
    out = inconclusive.check(
        "The data support neither equivalence nor an effect larger than the SESOI—external funding matters.",
        record=False,
    )
    assert _part(out.parts, "neither-equivalence").text == "neither equivalence nor an effect larger than the SESOI"
    assert any("external funding" in text for text in out.unchecked), str(out)


@pytest.mark.parametrize("sentence, expected", [
    ("The data support neither equivalence nor an effect larger than the smallest effect size of interest.",
     "neither equivalence nor an effect larger than the smallest effect size of interest"),
    ("The data support neither equivalence nor an effect larger than the long-term threshold of interest.",
     "neither equivalence nor an effect larger than the long-term threshold of interest"),
    ("Neither equivalence nor an effect greater than -1 points was shown.",
     "Neither equivalence nor an effect greater than -1 points"),
])
def test_dash_boundary_preserves_qualifiers_and_signed_numbers(inconclusive, sentence, expected):
    part = _part(_parts(inconclusive, sentence), "neither-equivalence")
    assert part.text == expected
    assert part.status == "check"
