"""Independent safety tests for group and time direction; not accuracy claims."""
import pytest
import statwarrant as sw


@pytest.fixture
def iris():
    return sw.declare(
        sesoi=1, sesoi_source="illustrative", units="cm", outcome="petal length",
        contrast="versicolor minus virginica",
    ).analyze(estimate=-1.292, se=0.1, df=80)


@pytest.fixture
def time_result():
    return sw.declare(
        sesoi=4, sesoi_source="illustrative", units="grams", outcome="weight",
        contrast="day 2 minus day 0 within chick",
    ).analyze(estimate=5.85, se=0.8, df=19)


def check(result, text):
    return result.check(text, record=False)


def no_wrong_direction_assurance(result, text):
    verdict = check(result, text)
    # A wrong (or unbound) directional assertion must trigger a relevant review
    # or conflict. A warning about a day/treatment number alone is insufficient.
    parts = verdict.parts
    assert any(
        p.status in {"check", "conflict"}
        and any(term in (p.rule + " " + p.reason).lower()
                for term in ("direction", "order", "compar", "contrast", "group", "operand"))
        for p in parts
    ), f"No relevant order/direction warning for {text!r}: {verdict}"
    assert not any(p.status == "consistent" and p.rule == "direction" for p in parts), str(verdict)


@pytest.mark.parametrize("text", [
    "The mean petal length was lower for virginica than for versicolor.",
    "Virginica had significantly lower petal length than versicolor.",
    "Virginica had a 1.292 cm lower mean petal length than versicolor.",
    "The mean petal length in virginica was lower than the mean in versicolor.",
])
def test_reversed_iris_does_not_clear_direction(iris, text):
    no_wrong_direction_assurance(iris, text)


@pytest.mark.parametrize("text", [
    "The mean petal length was higher for virginica than for versicolor.",
    "Virginica had significantly higher petal length than versicolor.",
])
def test_correct_reversed_form_is_not_mislabelled_as_conflict(iris, text):
    result = check(iris, text)
    assert not any(p.status == "conflict" and p.rule in {"direction", "significance"} for p in result.parts), str(result)


def test_reversed_time_does_not_treat_increased_as_supported(time_result):
    no_wrong_direction_assurance(time_result, "Mean chick weight increased from day 2 to day 0.")


def test_reversed_time_correct_decrease_not_direction_conflict(time_result):
    r = check(time_result, "Mean chick weight decreased from day 2 to day 0.")
    assert not any(p.status == "conflict" and p.rule == "direction" for p in r.parts), str(r)


def test_missing_contrast_requires_comparative_review():
    r = sw.declare(units="cm").analyze(estimate=-1.292, se=.1, df=80)
    no_wrong_direction_assurance(r, "The mean petal length was lower for virginica than for versicolor.")


def test_multiple_clauses_do_not_claim_logical_contradiction_automatically(iris):
    r = check(iris, "The mean petal length was lower for versicolor than virginica and higher for virginica than versicolor.")
    assert not any(p.status == "conflict" and p.rule == "direction" and "both directions" in p.reason.lower() for p in r.parts), str(r)


def test_simple_scalar_direction_still_available(iris):
    result = check(iris, "The effect estimate was negative.")
    assert any(p.rule == "direction" and p.status == "consistent" for p in result.parts), str(result)


def test_review_is_serialized_and_not_recorded(iris):
    before = len(iris.checked)
    verdict = iris.check("The mean petal length was lower for virginica than for versicolor.", record=False)
    assert len(iris.checked) == before
    d = verdict.to_dict()
    assert d["status"] == "warnings"
    assert any(v["status"] in ("check", "conflict") and v["spans"] and v["action"] for v in d["warnings"]), d


def test_folded_significance_does_not_hide_unbound_direction(iris):
    text = "The effect was statistically significant, and virginica was lower than versicolor."
    no_wrong_direction_assurance(iris, text)


def test_folded_significance_does_not_wrongly_conflict_for_supported_reverse(iris):
    text = "The effect was statistically significant, and virginica was higher than versicolor."
    result = check(iris, text)
    assert not any(p.status == "conflict" and p.rule in {"direction", "significance"} for p in result.parts), str(result)


def test_negated_comparison_does_not_assert_unnegated_token(iris):
    text = "The petal length of virginica was not lower than that of versicolor."
    result = check(iris, text)
    assert not any(p.status == "consistent" and p.rule == "direction" for p in result.parts), str(result)
    assert result.status != "no_warnings", str(result)


def test_unrelated_groups_cannot_be_inferred_from_polarity(iris):
    no_wrong_direction_assurance(iris, "Petal length was lower for setosa than for virginica.")


def test_review_part_is_visible_in_plain_text_and_json(iris):
    text = "The mean petal length was lower for virginica than for versicolor."
    verdict = check(iris, text)
    payload = verdict.to_dict()
    assert payload["status"] == "warnings"
    assert payload["warnings"], payload
    assert "warning" in str(verdict).lower(), str(verdict)


def test_nonzero_null_must_not_be_treated_as_raw_group_difference():
    from scipy import stats
    # Observations are paired A-minus-B differences, all near +3. The test is
    # against a null difference of +5, so statwarrant's adapted effect is near -2.
    # Its sign cannot safely be used as the sign of the original A-minus-B value.
    paired_differences = [3.0, 3.2, 2.8, 3.1, 2.9]
    r = sw.declare(contrast="group a minus group b", outcome="score").analyze(
        stats.ttest_1samp(paired_differences, popmean=5.0)
    )
    assert r.null == pytest.approx(5.0)
    text = "Score was lower for group a than for group b."
    no_wrong_direction_assurance(r, text)


def test_declared_slope_direct_sign_is_checked_as_scalar():
    r = sw.declare(contrast="OLS slope for x, not the intercept").analyze(estimate=1.0, se=0.1)
    result = check(r, "The slope was negative.")
    assert any(p.rule == "direction" and p.status == "conflict" for p in result.parts), str(result)


def test_named_slope_not_validated_if_declared_contrast_is_unrelated(iris):
    result = check(iris, "The slope was negative.")
    assert not any(p.rule == "direction" and p.status == "consistent" for p in result.parts), str(result)
    assert result.status == "warnings", str(result)


def test_nonzero_null_direct_estimate_sign_needs_review():
    from scipy import stats
    r = sw.declare(contrast="group a minus group b", outcome="score").analyze(
        stats.ttest_1samp([3.0, 3.2, 2.8, 3.1, 2.9], popmean=5.0)
    )
    out = check(r, "The effect estimate was negative.")
    assert out.status == "warnings"
    assert any(p.rule == "direction" and p.status == "check" for p in out.parts), str(out)
