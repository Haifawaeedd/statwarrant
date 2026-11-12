"""Properties that must hold for every input, checked with Hypothesis."""

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from statwarrant._core import evaluate

MIRROR = {
    "exceeds_sesoi_positive": "exceeds_sesoi_negative",
    "exceeds_sesoi_negative": "exceeds_sesoi_positive",
    "positive_importance_undetermined": "negative_importance_undetermined",
    "negative_importance_undetermined": "positive_importance_undetermined",
    "differs_positive": "differs_negative",
    "differs_negative": "differs_positive",
}
DECISIVE = {
    "exceeds_sesoi_positive", "exceeds_sesoi_negative", "nonzero_negligible", "equivalent",
    "positive_importance_undetermined", "negative_importance_undetermined",
}

estimates = st.floats(-3, 3, allow_nan=False)
ses = st.floats(0.01, 2)
bounds = st.floats(0.01, 2)
policies = st.sampled_from(["single", "standard"])


@settings(max_examples=400, deadline=None)
@given(estimates, ses, bounds, policies)
def test_sign_symmetry(est, se, d, policy):
    a = evaluate(est, se, None, 0.05, policy, (-d, d))
    b = evaluate(-est, se, None, 0.05, policy, (-d, d))
    assert b.claim_class == MIRROR.get(a.claim_class, a.claim_class)


@settings(max_examples=400, deadline=None)
@given(estimates, ses, bounds, policies, st.floats(0.01, 100))
def test_scale_invariance(est, se, d, policy, c):
    a = evaluate(est, se, None, 0.05, policy, (-d, d))
    b = evaluate(est * c, se * c, None, 0.05, policy, (-d * c, d * c))
    # skip inputs sitting within rounding distance of a decision boundary
    assume(min(abs(x) for x in (a.p_zero - 0.05, a.p_equivalence - a.equivalence_threshold,
                                a.p_minimal_effect - a.met_threshold)) > 1e-9)
    assert a.claim_class == b.claim_class


@settings(max_examples=400, deadline=None)
@given(estimates, ses, bounds, policies, st.floats(0.05, 1))
def test_more_precision_never_makes_a_decisive_result_inconclusive(est, se, d, policy, shrink):
    assume(abs(abs(est) - d) > 1e-6)
    a = evaluate(est, se, None, 0.05, policy, (-d, d))
    b = evaluate(est, se * shrink, None, 0.05, policy, (-d, d))
    if a.claim_class in DECISIVE:
        assert b.claim_class in DECISIVE
