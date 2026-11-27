"""0.6.1: a reply the reader cannot use is reported, never silently treated as "no claims"."""
import pytest

import statwarrant as sw
from statwarrant.llm import CallableLLM


@pytest.fixture
def res():
    return sw.declare(contrast="the drug minus placebo", outcome="survival", better="higher").analyze(
        estimate=1.0, se=1.0)


@pytest.mark.parametrize("reply", [
    '{"claims": [{"kind": "nonzero"}]}',          # wrong key
    '{"assertions": {"kind": "nonzero"}}',        # not a list
    '[{"kind": "nonzero"}]',                      # not an object
    '{}',
])
def test_reply_without_an_assertions_list_is_reported(res, reply):
    rv = res.review("The drug improved survival.", llm=CallableLLM(lambda s, u: reply), rewrite=True, record=False)
    assert rv.read_ok is False
    assert rv.verdicts == []
    assert any("assertions" in e for e in rv.errors)
    assert rv.suggestion is None
    assert rv.level != "no_warnings"
    assert rv.to_dict()["read_ok"] is False


def test_an_empty_assertions_list_is_a_valid_reading(res):
    rv = res.review("The trial enrolled 200 patients.",
                    llm=CallableLLM(lambda s, u: '{"assertions": [], "meaning": []}'), rewrite=False, record=False)
    assert rv.read_ok is True
    assert rv.errors == []


def test_provider_error_is_a_failed_reading(res):
    def boom(s, u):
        raise RuntimeError("timeout")
    rv = res.review("The drug improved survival.", llm=CallableLLM(boom), rewrite=True, record=False)
    assert rv.read_ok is False


def test_non_object_items_are_reported_but_others_are_kept(res):
    reply = '{"assertions": ["nonzero", {"kind": "nonzero", "direction": "positive", "polarity": "asserted"}]}'
    rv = res.review("The drug improved survival.", llm=CallableLLM(lambda s, u: reply), rewrite=False, record=False)
    assert rv.read_ok is True
    assert len(rv.verdicts) == 1
    assert any("not an object" in e for e in rv.errors)
