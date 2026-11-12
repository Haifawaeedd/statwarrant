"""Benchmark scenarios with known correct readings (alpha = 0.05, normal reference)."""

import pytest

from statwarrant._core import evaluate

SCENARIOS = {
    # name: (estimate, se, sesoi, expected class under "standard", under "single")
    "S1 meaningful positive": (0.60, 0.10, 0.2, "exceeds_sesoi_positive", "exceeds_sesoi_positive"),
    "S2 positive, importance open": (0.30, 0.10, 0.2, "positive_importance_undetermined", "positive_importance_undetermined"),
    "S3 nonzero but negligible": (0.08, 0.03, 0.2, "nonzero_negligible", "nonzero_negligible"),
    "S4 equivalent": (0.02, 0.05, 0.2, "equivalent", "equivalent"),
    "S5 inconclusive": (0.15, 0.20, 0.2, "inconclusive_both", "inconclusive_both"),
    "S6 meaningful harm": (-0.50, 0.10, 0.2, "exceeds_sesoi_negative", "exceeds_sesoi_negative"),
    # Equivalent with the 90% interval (standard) but the 95% interval crosses 0.2.
    "S7 level conflict": (0.10, 0.058, 0.2, "equivalent", "inconclusive_one_side"),
    # 0.1.0 called this "exceeds" under standard via the 90% interval; the
    # minimal-effect test now always uses alpha / 2 per direction.
    "S8 near the bound": (1.90, 1.00, 0.1, "inconclusive_one_side", "inconclusive_one_side"),
}


@pytest.mark.parametrize("name", SCENARIOS)
@pytest.mark.parametrize("policy", ["standard", "single"])
def test_scenario_classes(name, policy):
    est, se, d, standard, single = SCENARIOS[name]
    ev = evaluate(est, se, None, 0.05, policy, (-d, d))
    assert ev.claim_class == (standard if policy == "standard" else single)


def test_s7_conflict_is_flagged_only_under_standard_policy():
    std = evaluate(0.10, 0.058, None, 0.05, "standard", (-0.2, 0.2))
    one = evaluate(0.10, 0.058, None, 0.05, "single", (-0.2, 0.2))
    assert std.level_conflict and std.equivalent and std.zero_interval[1] > 0.2
    assert not one.level_conflict and not one.equivalent


def test_s8_minimal_effect_uses_alpha_over_two():
    for policy in ("standard", "single"):
        ev = evaluate(1.9, 1.0, None, 0.05, policy, (-0.1, 0.1))
        assert not ev.exceeds_sesoi and not ev.level_conflict
        assert ev.p_minimal_effect == pytest.approx(0.0359, abs=1e-4)  # one-sided, compared with 0.025


@pytest.mark.parametrize("est,cls", [(0.5, "differs_positive"), (-0.5, "differs_negative"), (0.1, "inconclusive_no_sesoi")])
def test_without_sesoi(est, cls):
    ev = evaluate(est, 0.1, None, 0.05, "single", None)
    assert ev.claim_class == cls
    assert ev.equivalent is None and ev.exceeds_sesoi is None
