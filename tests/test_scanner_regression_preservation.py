"""Regressions guarding original scanner behavior, not a general NLP evaluation.

No broadening of the scanner is assumed. Known detection gaps are made explicit
instead of being conflated with the two judgment-policy fixes.
"""

import json

import pytest
import statwarrant as sw


def _check(sentence, *, estimate=4, **options):
    return sw.declare(**options).analyze(estimate=estimate, se=1).check(sentence, record=False)


def _parts(out, rule):
    return [p for p in out.parts if p.rule == rule]


def _check_spans_and_serialization(out):
    data = json.loads(json.dumps(out.to_dict()))
    for part in out.parts:
        assert part.text == " … ".join(out.sentence[a:b] for a, b in part.spans)
        assert all(0 <= a < b <= len(out.sentence) for a, b in part.spans)
    assert data["status"] == out.status
    assert data["level"] == out.level
    assert data["unchecked"] == list(out.unchecked)


@pytest.mark.parametrize("sentence", [
    "The treatment was responsible for group A deaths.",
    "The treatment resulted in patients with cancer.",
])
def test_independent_causal_cues_remain_visible(sentence):
    out = _check(sentence, design="observational")
    assert out.level == "conflict"
    assert [p.status for p in _parts(out, "causal")] == ["conflict"]
    _check_spans_and_serialization(out)


def test_independent_size_cue_remains_visible():
    out = _check("The effect in patients with diabetes was small.",
                 subgroup="patients with diabetes", scope="patients with diabetes")
    assert out.level == "conflict"
    assert [p.status for p in _parts(out, "small")] == ["conflict"]
    _check_spans_and_serialization(out)


def test_not_established_wording_is_not_incorrectly_consistent():
    out = _check("The effect in patients without diabetes was not established.", estimate=0,
                 subgroup="men with diabetes", scope="men with diabetes")
    assert out.level == "check"
    assert [p.status for p in _parts(out, "not-established")] == ["check"]
    _check_spans_and_serialization(out)


def test_generic_group_is_unchecked_not_approved_as_subgroup():
    out = _check("The effect was significant in group A.", subgroup="group B")
    assert [(p.rule, p.status) for p in out.parts] == [("significance", "consistent")]
    assert any("group A" in fragment for fragment in out.unchecked)
    assert out.status == "no_warnings"
    assert "not a clearance" in str(out)
    _check_spans_and_serialization(out)


def test_existing_overlapping_cue_gap_is_not_misrepresented_as_fixed():
    out = _check("The treatment resulted in men with cancer.", design="observational")
    # The original scanner consumes "in men" as a subgroup hit before it can
    # recognize "resulted in". It asks for subgroup review but misses the causal
    # cue. The resulting warning is not an assessment of the causal claim.
    assert [p.status for p in _parts(out, "subgroup")] == ["check"]
    assert not _parts(out, "causal")
    assert any("resulted" in fragment for fragment in out.unchecked)
    _check_spans_and_serialization(out)
