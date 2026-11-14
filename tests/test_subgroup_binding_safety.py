"""Conservative handling of recognized subgroup phrases, not a general NLP test."""

import pytest

import statwarrant as sw


def _result(subgroup=None, **options):
    return sw.declare(subgroup=subgroup, **options).analyze(estimate=4, se=1)


def _subgroups(out):
    return [part for part in out.parts if part.rule == "subgroup"]


@pytest.mark.parametrize(
    "declared,sentence",
    [
        ("men with diabetes", "The effect was significant in women with diabetes."),
        ("women with diabetes", "The effect was significant in men with diabetes."),
        ("men with diabetes", "The effect was significant in men without diabetes."),
        ("men without diabetes", "The effect was significant in men with diabetes."),
        ("men with diabetes", "The effect was significant in men with cancer."),
        ("men with T2DM", "The effect was significant in men with T1DM."),
        ("men with diabetes", "The effect was significant in men with diabetes and women with diabetes."),
        ("men with diabetes", "The effect was significant in men with diabetes or in women with diabetes."),
        ("men with diabetes", "The effect was significant in women, not men with diabetes."),
        ("men with diabetes", "The effect was significant in men with diabetes, but not women with diabetes."),
        ("men with diabetes", "The effect was significant not in men with diabetes, but in women with diabetes."),
        ("patients receiving no respiratory support",
         "Among patients who were not receiving respiratory support, no benefit was evident."),
    ],
)
def test_recognized_subgroups_need_review_even_when_words_overlap(declared, sentence):
    out = _result(declared, scope=declared).check(sentence, record=False)
    parts = _subgroups(out)
    assert parts, str(out)
    assert all(part.status == "check" for part in parts), str(out)
    assert out.status == "warnings", str(out)
    assert not any(part["rule"] == "subgroup" for part in out.to_dict()["consistent"])


def test_reported_example_serialization_and_exact_offsets():
    sentence = "The effect was significant in women with diabetes."
    out = _result("men with diabetes", scope="men with diabetes").check(sentence, record=False)
    data = out.to_dict()
    assert out.status == data["status"] == "warnings"
    assert out.level == data["level"] == "check"
    assert [(part["rule"], part["status"]) for part in data["warnings"]] == [("subgroup", "check")]
    assert [(part["rule"], part["status"]) for part in data["consistent"]] == [("significance", "consistent")]
    assert data["conflicts"] == [] and data["to_verify"] == data["warnings"]
    subgroup = data["warnings"][0]
    assert "men with diabetes" in subgroup["reason"]
    assert "by hand" in subgroup["reason"] and subgroup["action"]
    assert [sentence[start:end] for start, end in subgroup["spans"]] == [subgroup["text"]]
    assert any("diabetes" in fragment for fragment in data["unchecked"])


def test_exact_positive_control_is_still_review_not_pass():
    sentence = "The effect was significant in men with diabetes."
    out = _result("men with diabetes", scope="men with diabetes").check(sentence, record=False)
    assert out.status == "warnings" and out.level == "check"
    assert [part.status for part in _subgroups(out)] == ["check"]
    assert "Not verified" in str(out) and "not a clearance" in str(out)


def test_undeclared_subgroup_needs_review_even_if_scope_names_it():
    out = _result(scope="men with diabetes").check(
        "The effect was significant in men with diabetes.", record=False
    )
    assert out.status == "warnings" and out.level == "check"
    assert [part.status for part in _subgroups(out)] == ["check"]
    assert "declare subgroup" in _subgroups(out)[0].reason


def test_no_subgroup_wording_preserves_independent_significance_check():
    out = _result("men with diabetes").check("The effect was significant.", record=False)
    assert out.status == "no_warnings" and out.level is None
    assert [(part.rule, part.status) for part in out.parts] == [("significance", "consistent")]
    assert not _subgroups(out)
    assert "not a clearance" in str(out)


def test_independent_significance_conflict_is_not_suppressed():
    result = sw.declare(subgroup="men with diabetes").analyze(estimate=0, se=1)
    out = result.check("The effect was significant in women with diabetes.", record=False)
    parts = {part.rule: part.status for part in out.parts}
    assert parts["subgroup"] == "check" and parts["significance"] == "conflict"
    assert out.status == "warnings" and out.level == "conflict"


def test_independent_numeric_conflict_is_not_suppressed():
    sentence = "The effect was significant in men with diabetes; the estimate was 99."
    out = _result("men with diabetes").check(sentence, record=False)
    parts = {part.rule: part.status for part in out.parts}
    assert parts["subgroup"] == "check" and parts["significance"] == "consistent"
    assert parts["reported-number"] == "conflict" and out.level == "conflict"
    assert any(sentence[a:b] == "99" for part in out.conflicts for a, b in part.spans)


def test_independent_causal_conflict_is_not_suppressed():
    sentence = "Among men with diabetes, the treatment caused mortality."
    out = _result("men with diabetes", design="observational").check(sentence, record=False)
    parts = {part.rule: part.status for part in out.parts}
    assert parts["subgroup"] == "check" and parts["causal"] == "conflict"
    assert out.status == "warnings" and out.level == "conflict"


def test_unchecked_compound_tail_remains_visible():
    sentence = "The effect was significant in men with diabetes and women with diabetes."
    out = _result("men with diabetes").check(sentence, record=False)
    assert _subgroups(out)[0].status == "check"
    assert any("women with diabetes" in fragment for fragment in out.unchecked)
    assert any("women with diabetes" in fragment for fragment in out.to_dict()["unchecked"])


def test_exact_contrast_group_arms_are_not_mistaken_for_subgroups():
    result = sw.declare(contrast="group a minus group ab", outcome="scores").analyze(estimate=-0.6, se=0.1)
    out = result.check("Scores were lower for group a than for group ab.", record=False)
    assert out.status == "no_warnings" and not _subgroups(out)
    assert [(part.rule, part.status) for part in out.parts] == [("direction", "consistent")]
    extended = result.check("Scores were lower for group a than for group ab and for group c.", record=False)
    assert extended.status == "warnings"
    # The original scanner does not recognize generic "group c"; the direction
    # warning must not be mistaken for verification of that unchecked group.
    assert not _subgroups(extended)
    assert any("group c" in fragment for fragment in extended.unchecked)
    assert any(part.rule == "direction" and part.status == "check" for part in extended.parts)


@pytest.mark.parametrize("declared,sentence,fragment", [
    ("group A", "The effect was significant in group B.", "group B"),
    ("patients with diabetes", "The effect was significant in patients with T2DM.", "patients with T2DM"),
    ("men with diabetes", "Women with diabetes had a significant effect.", "Women with diabetes"),
])
def test_unrecognized_subgroup_phrases_remain_unchecked(declared, sentence, fragment):
    # These genuine detection gaps remain, rather than using a new pattern that
    # can swallow causal or size wording. No warning is not an approval.
    out = _result(declared).check(sentence, record=False)
    assert not _subgroups(out)
    assert any(fragment in part for part in out.unchecked)
    assert not any(part.rule == "subgroup" and part.status == "consistent" for part in out.parts)


def test_unrecognized_subgroup_wording_remains_unchecked_not_implicitly_verified():
    # The subgroup detector is deliberately incomplete; no warning is not a clearance.
    sentence = "The effect was significant in diabetics."
    out = _result("men with diabetes").check(sentence, record=False)
    assert not _subgroups(out)
    assert out.status == "no_warnings" and out.level is None
    assert any("diabetics" in fragment for fragment in out.unchecked)
    assert "not a clearance" in str(out)
