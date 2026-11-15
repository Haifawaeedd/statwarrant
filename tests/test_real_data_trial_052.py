"""0.5.2: fixes from the MIA5150 real-data trial (direction, guarantees, 'all <noun>', two-sided significance)."""
import pytest

import statwarrant as sw


def parts(result, rule):
    return [p.status for p in result.parts if p.rule == rule]


@pytest.fixture
def positive():
    # A clear, significant gain: evidence minus baseline = +13 points of accuracy.
    return sw.declare(sesoi=0.01, sesoi_source="illustrative", units="proportion", outcome="accuracy",
                      contrast="evidence minus baseline").analyze(estimate=0.13, se=0.013, df=999)


@pytest.fixture
def unclear():
    # Trial case: estimate -1.6 points, 95% CI includes zero.
    return sw.declare(sesoi=0.01, sesoi_source="illustrative", units="proportion", outcome="accuracy",
                      contrast="S300 minus C1").analyze(estimate=-0.016, se=0.01066, df=999)


# --- direction -------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["Adding evidence reduced accuracy.", "Evidence lowered accuracy.",
                                  "Accuracy was lower with evidence.",
                                  "Evidence significantly reduced accuracy."])
def test_reversed_direction_named_by_first_label_is_a_conflict(positive, text):
    assert "conflict" in parts(positive.check(text, record=False), "direction")


@pytest.mark.parametrize("text", ["Adding evidence improved accuracy.", "Accuracy was higher with evidence."])
def test_matching_direction_is_never_confirmed_only_sent_to_review(positive, text):
    assert parts(positive.check(text, record=False), "direction") == ["check"]


@pytest.mark.parametrize("text", [
    "Removing evidence reduced accuracy.",           # the label is removed, so the sign flips
    "Without evidence, accuracy dropped.",
    "Less evidence improved accuracy.",
    "Compared with baseline, accuracy improved.",   # the second label or a comparison cue
    "Accuracy improved with evidence compared with baseline.",
    "Evidence reduced errors.",                      # the declared outcome is not named
    "Accuracy improved.",                            # no label at all
])
def test_unclear_binding_stays_with_the_reviewer(positive, text):
    assert "conflict" not in parts(positive.check(text, record=False), "direction")
    assert "consistent" not in parts(positive.check(text, record=False), "direction")


def test_stated_change_with_interval_including_zero_conflicts_whichever_way(unclear):
    out = unclear.check("Adding justification significantly improved GPT accuracy.", record=False)
    assert "conflict" in parts(out, "direction")
    assert "conflict" in parts(out, "significance")


def test_comparatives_still_need_review_when_direction_is_unclear(unclear):
    # "higher" may compare something other than the declared contrast.
    assert parts(unclear.check("Scores were slightly higher.", record=False), "direction") != ["conflict"]


def test_small_point_estimate_beyond_sesoi_is_not_called_small(unclear):
    out = unclear.check("The estimated difference was small and its confidence interval included zero.",
                        record=False)
    assert parts(out, "small") == ["conflict"]


# --- guarantees and 'all <noun>' -------------------------------------------------------------

def test_guarantee_on_all_questions_is_flagged(positive):
    out = positive.check("The model is guaranteed to be accurate on all medical questions.", record=False)
    assert parts(out, "certainty") == ["conflict"]
    assert parts(out, "generalization") == ["conflict"]


@pytest.mark.parametrize("text", ["Accuracy is not guaranteed.", "This does not guarantee better accuracy."])
def test_negated_guarantee_is_a_caution(positive, text):
    out = positive.check(text, record=False)
    assert "conflict" not in parts(out, "certainty")
    assert parts(out, "caution") == ["consistent"]


def test_counted_groups_are_not_a_generalisation(positive):
    out = positive.check("Results were similar in all three groups.", record=False)
    assert parts(out, "generalization") == []


# --- two-sided significance ------------------------------------------------------------------

@pytest.mark.parametrize("text", ["There was a significant difference between the groups.",
                                  "Scores differed significantly between groups."])
def test_nondirectional_significance_matches_a_significant_result(text):
    res = sw.declare(sesoi=0.01, sesoi_source="illustrative").analyze(estimate=0.13, se=0.013, df=999)
    assert parts(res.check(text, record=False), "significance") == ["consistent"]


def test_nondirectional_significance_conflicts_with_a_nonsignificant_result(unclear):
    out = unclear.check("There was a significant difference between the conditions.", record=False)
    assert parts(out, "significance") == ["conflict"]


@pytest.mark.parametrize("text", ["Scores were significantly higher than in the control group.",
                                  "Survival time was significantly longer for treatment than control."])
def test_directional_significance_is_not_confirmed_without_binding(text):
    res = sw.declare(contrast="treatment minus control").analyze(estimate=0.13, se=0.013, df=999)
    assert "consistent" not in parts(res.check(text, record=False), "significance")


@pytest.mark.parametrize("text", ["We could not determine whether adding evidence improved accuracy.",
                                  "It is unclear if the new prompt reduced accuracy."])
def test_a_change_asked_about_is_not_asserted(unclear, text):
    assert "conflict" not in parts(unclear.check(text, record=False), "direction")


def test_a_named_direction_keeps_significance_with_the_reviewer():
    res = sw.declare(sesoi=0.01, sesoi_source="illustrative").analyze(estimate=0.13, se=0.013, df=999)
    out = res.check("There was a significant inverse association between coffee and mortality.", record=False)
    assert "consistent" not in parts(out, "significance")
