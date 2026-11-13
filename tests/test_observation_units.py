"""Targeted unit regressions, not a benchmark or sentence-wide validation."""

import json

import pytest

import statwarrant as sw


@pytest.fixture
def sleep():
    # Same summary as the external paired-sleep review; real observations are
    # exercised separately by its audit reproducer.
    return sw.declare(units="hours", outcome="extra sleep").analyze(
        estimate=1.58, se=0.3889587238883952, df=9
    )


def check(result, sentence):
    return result.check(sentence, record=False)


def numeric_parts(result):
    return [p for p in result.parts if p.rule in ("reported-number", "magnitude")]


def test_exact_external_review_original_sentences(sleep):
    correct = check(sleep, "The effect was approximately 1.58 hours.")
    different = check(sleep, "The effect was approximately 1.58 minutes.")
    assert correct.status == "no_warnings"
    assert [(p.rule, p.status) for p in numeric_parts(correct)] == [("reported-number", "consistent")]
    assert different.status == "warnings" and different.level == "check"
    assert [(p.rule, p.status) for p in numeric_parts(different)] == [("reported-number", "check")]
    part = numeric_parts(different)[0]
    assert [different.sentence[a:b] for a, b in part.spans] == ["1.58", "minutes"]
    assert "conversion" in part.reason and "conversion" in part.action
    assert "not a clearance" in str(correct)
    assert "not proof" in str(different)


@pytest.mark.parametrize("declared", ["hour", "hours", "hr", "hrs", "HrS"])
@pytest.mark.parametrize("written", ["hour", "hours", "hr", "hrs", "HOURS"])
def test_safe_hour_synonyms(declared, written):
    result = sw.declare(units=declared).analyze(estimate=1.58, se=0.3, df=9)
    out = check(result, f"The estimate was approximately 1.58 {written}.")
    assert out.status == "no_warnings", str(out)
    assert numeric_parts(out)[0].status == "consistent"
    assert "adjacent simple unit matches" in numeric_parts(out)[0].reason


@pytest.mark.parametrize("text", ["1.58 minutes", "94.8 minutes", "95.8 minutes", "1.58 seconds",
                                  "1.58 kilograms", "1.58 metres", "1.58 points"])
def test_different_units_require_check_not_unconverted_conflict(sleep, text):
    out = check(sleep, f"The effect was approximately {text}.")
    assert out.level == "check", str(out)
    assert numeric_parts(out)[0].status == "check"
    assert not any(p.status == "consistent" for p in numeric_parts(out))
    assert "has not been compared across scales" in numeric_parts(out)[0].reason
    assert "wrong" not in numeric_parts(out)[0].reason.lower()


@pytest.mark.parametrize("written", ["1.58 hours", "1.60 hours", "94.8 hours"])
def test_reverse_conversion_is_not_approved(written):
    result = sw.declare(units="minutes").analyze(estimate=94.8, se=23.3375, df=9)
    out = check(result, f"The estimate was {written}.")
    assert out.level == "check"
    assert numeric_parts(out)[0].status == "check"


def test_wrong_number_in_same_units_preserves_existing_numeric_judgment(sleep):
    out = check(sleep, "The effect was approximately 94.8 hours.")
    assert numeric_parts(out)[0].status == "conflict"


@pytest.mark.parametrize("written", ["94.8 m", "1.58 h", "1.58 s", "1.58 g"])
def test_ambiguous_abbreviations_are_not_converted_or_approved(sleep, written):
    out = check(sleep, f"The effect was {written}.")
    assert out.level == "check", str(out)
    assert numeric_parts(out)[0].status == "check"


def test_magnitude_by_number_attaches_only_its_own_unit(sleep):
    same = check(sleep, "Sleep increased by 1.58 hours.")
    different = check(sleep, "Sleep increased by 94.8 minutes.")
    assert next(p for p in same.parts if p.rule == "magnitude").status == "consistent"
    assert next(p for p in different.parts if p.rule == "magnitude").status == "check"


@pytest.mark.parametrize("declared", [None, "furlongs", "hours per day", "m", " "])
def test_missing_unsupported_or_ambiguous_declared_unit_does_not_validate(declared):
    result = sw.declare(units=declared).analyze(estimate=1.58, se=0.3, df=9)
    out = check(result, "The effect was 1.58 hours.")
    assert out.level == "check", str(out)
    assert numeric_parts(out)[0].status == "check"
    assert "missing, compound, or not supported" in numeric_parts(out)[0].reason


def test_unknown_written_unit_remains_unchecked_not_verified(sleep):
    out = check(sleep, "The effect was 1.58 furlongs.")
    assert any("furlongs" in part for part in out.unchecked)
    assert "numeric comparison only" in numeric_parts(out)[0].reason
    assert "partial" in str(out) and "unchecked" in out.to_dict()["unit_check_note"]


@pytest.mark.parametrize("text", ["hours per day", "hours/day", "hour-long"])
def test_compound_written_units_do_not_match_simple_declared_hours(sleep, text):
    out = check(sleep, f"The effect was 1.58 {text}.")
    assert numeric_parts(out)[0].status == "check", str(out)


def test_every_check_and_report_disclose_partial_unit_coverage(sleep):
    unsupported = check(sleep, "We used a mixed design.")
    assert unsupported.status == "no_supported_pattern"
    assert "Unit checking is pattern-based and partial" in str(unsupported)
    assert "may be unchecked" in unsupported.to_dict()["unit_check_note"]
    sleep.check("The effect was approximately 1.58 hours.")
    assert "Units and conversions" in sleep.to_markdown()
    doc = json.loads(sleep.to_json())
    assert "partial" in doc["checked_sentences"][0]["unit_check_note"]
    assert any("Units and conversions" in item for item in doc["not_verified"])


def test_adjacent_estimate_only_not_p_df_or_interval(sleep):
    sentence = "The effect was 1.58 hours, 95% CI [0.70, 2.46], p = 0.00283, df = 9."
    out = check(sleep, sentence)
    assert out.status == "no_warnings", str(out)
    assert {p.rule for p in out.parts} >= {"reported-number", "interval-level", "range", "p-value"}
    pvalue = next(p for p in out.parts if p.rule == "p-value")
    df = next(p for p in out.parts if p.rule == "reported-number" and p.text == "9")
    interval = next(p for p in out.parts if p.rule == "range")
    assert pvalue.status == df.status == interval.status == "consistent"
    assert not any("adjacent simple unit" in p.reason for p in (pvalue, df, interval))


@pytest.mark.parametrize("sentence,rule", [
    ("The p-value was 0.00283 minutes.", "p-value"),
    ("The df was 9 minutes.", "reported-number"),
    ("The 95% CI was [0.70, 2.46] minutes.", "range"),
])
def test_other_statistic_units_remain_explicitly_unchecked(sleep, sentence, rule):
    out = check(sleep, sentence)
    part = next(p for p in out.parts if p.rule == rule)
    assert "adjacent simple unit" not in part.reason
    assert any("minutes" in fragment for fragment in out.unchecked)
    assert "may be unchecked" in out.to_dict()["unit_check_note"]


def test_clause_local_pairs_are_not_cross_bound(sleep):
    out = check(sleep, "The effect was 1.58 minutes; the effect was 1.58 hours.")
    numbers = numeric_parts(out)
    assert len(numbers) == 2
    assert numbers[0].status == "check" and "minutes" in numbers[0].text
    assert numbers[1].status == "consistent" and "hours" in numbers[1].text
    out = check(sleep, "The effect was 1.58 hours and 1.58 minutes.")
    assert any(p.rule == "unverified-number" and p.status == "check" for p in out.parts)
    assert not any("minutes" in p.text and p.status == "consistent" for p in out.parts)


def test_multiple_models_require_review_not_implicit_binding(sleep):
    out = check(sleep, "The effect was 1.58 hours for model A and 1.58 minutes for model B.")
    assert out.level == "check"
    assert not any(p.rule in ("reported-number", "magnitude") and p.status == "consistent" for p in out.parts)
    assert "model" in numeric_parts(out)[0].reason
    compact = check(sleep, "The effect was 1.58 hours for model A and B.")
    assert numeric_parts(compact)[0].status == "check"


def test_outcome_names_do_not_create_an_effect_unit_or_direction():
    result = sw.declare(units="hours", outcome="sleep improvement").analyze(estimate=1.58, se=0.3, df=9)
    out = check(result, "The effect on sleep improvement was approximately 1.58 minutes.")
    assert not any(p.rule == "direction" for p in out.parts)
    # This particular phrasing is outside the recognised estimate pattern.
    assert any(p.rule == "unverified-number" and p.status == "check" for p in out.parts)
    assert any("minutes" in fragment for fragment in out.unchecked)


def test_negated_quantity_is_not_approved(sleep):
    out = check(sleep, "The effect was not 1.58 minutes.")
    assert out.level == "check"
    assert any(p.rule == "unattached-negation" for p in out.warnings)
    assert not any(p.status == "consistent" for p in numeric_parts(out))


def test_other_words_are_not_silently_approved(sleep):
    out = check(sleep, "The effect was 1.58 minutes and the treatment is safe.")
    assert out.level == "check"
    assert any("safe" in item for item in out.unchecked)
    assert "not proof" in str(out)


def test_percentage_points_and_percent_paths_remain_distinct():
    acc = sw.declare(units="accuracy").analyze(estimate=0.009259, se=0.008069, df=539)
    converted = check(acc, "The advantage was 0.9 percentage points.")
    assert converted.status == "no_warnings", str(converted)
    assert any("percentage points" in p.reason for p in converted.parts)
    assert check(acc, "The advantage was 9 percentage points.").level == "conflict"
    hours = sw.declare(units="hours").analyze(estimate=0.009259, se=0.008069, df=539)
    assert check(hours, "The advantage was 0.9 percentage points.").level == "check"
    assert check(hours, "The advantage was 0.9%.").level == "check"
    points = sw.declare(units="points").analyze(estimate=1.58, se=0.3, df=9)
    assert check(points, "The effect was 1.58 points.").status == "no_warnings"
    assert check(points, "The effect was 1.58 minutes.").level == "check"
