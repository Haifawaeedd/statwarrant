import json

import pytest

import statwarrant as sw
from statwarrant._core import evaluate
from statwarrant.claims import Context, build_claims, check_sentence

from test_scenarios import SCENARIOS


def ctx_for(est, se, d=0.2, policy="single", **kw):
    return Context(evaluate(est, se, None, 0.05, policy, None if d is None else (-d, d)), **kw)


@pytest.mark.parametrize("name", SCENARIOS)
@pytest.mark.parametrize("policy", ["single", "standard"])
def test_allowed_claims_never_fail_the_checker(name, policy):
    est, se, d, *_ = SCENARIOS[name]
    ctx = ctx_for(est, se, d, policy, units="points", scope="one cohort")
    claims = build_claims(ctx)
    assert claims.allowed
    for c in claims.allowed:
        assert check_sentence(c.text, ctx).status == "no_warnings", str(check_sentence(c.text, ctx))


@pytest.mark.parametrize("name", SCENARIOS)
def test_no_effect_is_always_blocked(name):
    est, se, d, *_ = SCENARIOS[name]
    for s in ["There is no effect.", "There was no difference."]:
        assert check_sentence(s, ctx_for(est, se, d)).level == "conflict", s


@pytest.mark.parametrize("name", SCENARIOS)
def test_negated_direction(name):
    est, se, d, *_ = SCENARIOS[name]
    ctx = ctx_for(est, se, d)
    level = check_sentence("The intervention did not improve scores.", ctx).level
    # Literally true only when the data show the opposite direction; never without a warning.
    assert level == ("check" if ctx.evidence.direction == -1 else "conflict")


def test_nonsignificance_wording_needs_care_or_is_blocked():
    insig = ctx_for(0.15, 0.2)
    sig = ctx_for(0.6, 0.1)
    s = "The difference was not statistically significant."
    assert check_sentence(s, insig).level == "check"
    assert check_sentence(s, sig).level == "conflict"


def test_equivalence_claim_only_when_established():
    s = "The two methods are equivalent."
    assert check_sentence(s, ctx_for(0.02, 0.05)).status == "no_warnings"
    assert check_sentence(s, ctx_for(0.08, 0.03)).status == "no_warnings"  # nonzero but negligible
    assert check_sentence(s, ctx_for(0.15, 0.2)).level == "conflict"
    assert check_sentence(s, ctx_for(0.02, 0.05, d=None)).level == "conflict"


def test_importance_and_direction():
    pos = ctx_for(0.6, 0.1)
    # Exceeding the SESOI supports "important", not "large".
    assert check_sentence("The program produced a large improvement.", pos).level == "check"
    assert check_sentence("The program produced a meaningful improvement.", pos).status == "no_warnings"
    assert check_sentence("The program produced a large decrease.", pos).level == "conflict"
    # Without a declared contrast the comparison's direction is not bound.
    assert check_sentence("Scores were lower with the program.", pos).level == "check"
    # "Substantial" has no defined magnitude scale, so require review rather
    # than equating it with an assertion of exceeding the SESOI.
    assert check_sentence("The program had a substantial effect.", ctx_for(0.3, 0.1)).level == "check"


def test_better_lower_flips_improvement_words():
    # error rate went down by 0.5: with better="lower", "improved" is supported
    ctx = ctx_for(-0.5, 0.1, better="lower")
    assert check_sentence("The new model improved the error rate.", ctx).status == "no_warnings"
    # "Worse" is comparative, but this sentence does not bind a contrast.
    assert check_sentence("The new model made the error rate worse.", ctx).level == "check"


def test_significance_claims():
    assert check_sentence("The effect is statistically significant.", ctx_for(0.3, 0.1)).status == "no_warnings"
    assert check_sentence("The effect is statistically significant.", ctx_for(0.15, 0.2)).level == "conflict"
    assert check_sentence("Scores significantly decreased.", ctx_for(0.3, 0.1)).level == "conflict"


def test_generalization_certainty_percentage_unrecognized():
    ctx = ctx_for(0.6, 0.1, scope="grade 9, two schools")
    gen = check_sentence("This works for all students.", ctx)
    assert gen.level == "conflict" and any("grade 9" in p.reason for p in gen.warnings)
    assert check_sentence("These results prove the method works.", ctx).level == "conflict"
    pct = check_sentence("Scores rose by 20%.", Context(ctx.evidence, baseline=3.0))
    assert pct.level == "check" and "+20.0%" in " ".join(p.reason for p in pct.warnings)
    assert check_sentence("We used a mixed design.", ctx).status == "no_supported_pattern"


def test_level_conflict_note_and_json():
    plan = sw.declare(sesoi=0.2, sesoi_source="pilot", interval_policy="standard")
    res = plan.analyze(estimate=0.10, se=0.058)
    assert any("Level conflict" in n for n in res.claims.notes)
    data = json.loads(res.to_json())
    assert data["evidence"]["level_conflict"] is True
    assert data["plan"]["sesoi_source"] == "pilot"


def test_markdown_contains_both_lists():
    plan = sw.declare(sesoi=3, sesoi_source="teachers", units="points", scope="one term")
    md = plan.analyze(estimate=4.2, se=1.6, df=58, baseline=60).to_markdown()
    assert "### You can say" in md and "### Do not say" in md
    assert "relative change" in md
