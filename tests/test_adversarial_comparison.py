"""Regression cases identified by a separate code review."""
import pytest
import statwarrant as sw


def check(result, text):
    return result.check(text, record=False)


@pytest.fixture
def treatment():
    return sw.declare(contrast="treatment minus control", outcome="score", units="points").analyze(
        estimate=-5, se=1
    )


@pytest.mark.parametrize("text", [
    "The control minus treatment difference was -5 points.",
    "The control minus treatment difference was 5 points.",
    "The effect was -5 points, but treatment outscored control.",
])
def test_unbound_numeric_group_order_needs_relevant_review(treatment, text):
    result = check(treatment, text)
    assert result.status == "warnings", str(result)
    assert any(p.status == "check" and any(w in (p.reason + p.rule).lower() for w in
               ("contrast", "compar", "order", "direction")) for p in result.parts), str(result)
    assert not any(p.status in ("conflict", "consistent") and p.rule == "reported-number"
                   for p in result.parts), str(result)


def test_direction_embedded_in_nonsignificance_is_not_wrong_conflict():
    r = sw.declare(contrast="post minus pre", outcome="scores").analyze(estimate=-5, se=1)
    for text in ("Scores did not increase significantly from pre to post.",
                 "Scores did not significantly increase from pre to post."):
        result = check(r, text)
        assert result.status == "warnings", str(result)
        assert any(p.status == "check" and p.rule in ("direction", "nonsignificance") for p in result.parts), str(result)
        assert not any(p.status == "conflict" and p.rule in ("nonsignificance", "direction") for p in result.parts), str(result)


@pytest.mark.parametrize("text", ["Scores decreased post-treatment.", "Scores increased post-treatment.",
                                  "Scores decreased postprocedure.", "Scores improved during follow-up."])
def test_unbound_implicit_temporal_comparison_needs_review(text):
    r = sw.declare().analyze(estimate=-5, se=1)
    result = check(r, text)
    assert any(p.status == "check" and p.rule == "direction" for p in result.parts), str(result)
    assert not any(p.status in ("conflict", "consistent") and p.rule == "direction" for p in result.parts), str(result)


def test_unrecognized_comparative_word_must_not_lend_significance_reassurance(treatment):
    text = "Survival time was significantly longer for treatment than control."
    result = check(treatment, text)
    assert result.status == "warnings", str(result)
    assert not any(p.status == "consistent" and p.rule == "significance" for p in result.parts), str(result)
    assert any(p.status == "check" and p.rule in ("direction", "significance") for p in result.parts), str(result)


@pytest.mark.parametrize("text, expected", [
    ("The 95% CI was between 1.0 and 7.4.", "consistent"),
    ("The 95% CI was between -7.4 and -1.0.", "conflict"),
    ("The 95% CI was between 7.4 and 1.0.", "conflict"),
])
def test_numeric_interval_between_does_not_imply_unbound_groups(text, expected):
    r = sw.declare(contrast="treatment minus control", units="points").analyze(estimate=4.2, se=1.6, df=58)
    out = check(r, text)
    assert any(p.rule == "range" and p.status == expected for p in out.parts), str(out)


@pytest.mark.parametrize("text, expected", [
    ("The effect is positive and statistically significant.", "consistent"),
    ("The effect is negative and statistically significant.", "conflict"),
])
def test_direct_compound_scalar_sign_is_assessed(text, expected):
    r = sw.declare(contrast="treatment minus control").analyze(estimate=4.2, se=1.6, df=58)
    out = check(r, text)
    assert any(p.rule in ("significance", "direction") and p.status == expected for p in out.parts), str(out)
