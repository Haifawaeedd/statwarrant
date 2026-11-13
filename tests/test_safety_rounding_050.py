"""Safety regressions for uncertainty about printed interval precision.

The existing symmetry acceptance rule is deliberately retained; these tests
separate its assumptions from facts about the original publication.
"""

import json
import math
import re
from decimal import Decimal, ROUND_HALF_UP

import pytest
from scipy import stats

import statwarrant as sw


def _difference_note(result):
    return next(note for note in result.raw_input["provenance_notes"] if "estimate given" in note)


def _interval_note(result):
    return next(note for note in result.raw_input["provenance_notes"] if "input interval" in note)


def test_mixed_precision_cannot_be_ruled_out_by_float_inputs():
    # An actually symmetric interval with mixed printed precision is a concrete
    # counterexample to the idea that rounding cannot explain the discrepancy.
    lo, hi = Decimal("1.04"), Decimal("7.44")
    assert (lo + hi) / 2 == Decimal("4.24")
    assert lo.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) == Decimal("1.0")
    assert hi.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) == Decimal("7.4")

    result = sw.declare().analyze(estimate=4.24, ci=(1.0, 7.4))
    info, note = result.raw_input["estimate_vs_midpoint"], _difference_note(result)
    assert info["explained_by_rounding"] is None
    assert info["within_assumed_rounding_allowance"] is False
    assert info["assumed_decimal_places"] == 2
    assert info["assumed_rounding_allowance"] == pytest.approx(0.01)
    assert "Printed precision is unknown" in note
    assert "assumes a common precision of 2 decimal places" in note
    assert "rounding actually explains the difference is unknown" in note
    assert "check that the estimate and the interval belong together" in note
    assert result.raw_input["estimate"] == 4.24
    assert result.raw_input["ci"] == [1.0, 7.4]
    assert result.evidence.estimate == pytest.approx(4.2)


def test_original_44_regression_uses_assumed_not_certain_precision():
    result = sw.declare().analyze(estimate=4.4, ci=(1.0, 7.4))
    info, note = result.raw_input["estimate_vs_midpoint"], _difference_note(result)
    assert info["explained_by_rounding"] is None
    assert info["within_assumed_rounding_allowance"] is False
    assert info["assumed_decimal_places"] == 1
    assert info["assumed_rounding_allowance"] == pytest.approx(0.1)
    assert all(text in note for text in ("4.4", "4.2", "0.2", "0.1", "gap exceeds"))
    assert "unknown" in note and "check that the estimate" in note
    assert result.evidence.estimate == pytest.approx(4.2)
    assert result.evidence.se == pytest.approx(3.2 / stats.norm.ppf(0.975))
    assert result.evidence.p_zero == pytest.approx(2 * stats.norm.sf(4.2 / result.evidence.se))


def test_within_heuristic_allowance_is_not_a_causal_finding():
    result = sw.declare().analyze(estimate=4.3, ci=(1.0, 7.4))
    info, note = result.raw_input["estimate_vs_midpoint"], _difference_note(result)
    assert info["within_assumed_rounding_allowance"] is True
    assert info["explained_by_rounding"] is None
    assert "gap is within" in note
    assert "actually explains the difference is unknown" in note
    assert "no more than rounding of the printed numbers explains" not in note


@pytest.mark.parametrize("scale", [1e-6, 1e-12])
def test_scientific_float_repr_does_not_prove_zero_printed_rounding(scale):
    result = sw.declare().analyze(estimate=4.24 * scale, ci=(scale, 7.4 * scale))
    info, note = result.raw_input["estimate_vs_midpoint"], _difference_note(result)
    assert info["assumed_decimal_places"] is None
    assert info["assumed_rounding_allowance"] == 0.0  # Existing policy, not known source precision.
    assert info["explained_by_rounding"] is None
    assert info["within_assumed_rounding_allowance"] is False
    assert "zero rounding allowance" in note and "scientific notation" in note
    assert "Printed precision is unknown" in note
    assert "actually explains the difference is unknown" in note
    assert result.evidence.estimate == pytest.approx(4.2 * scale)


def test_equivalent_float_values_cannot_disclose_original_spelling():
    a = sw.declare().analyze(estimate=4.24, ci=(float("1.0"), 7.4))
    b = sw.declare().analyze(estimate=4.24, ci=(float("1.00"), 7.4))
    assert a.raw_input["estimate_vs_midpoint"] == b.raw_input["estimate_vs_midpoint"]
    assert "trailing zeros" in _difference_note(a)


@pytest.mark.parametrize("estimate,accepted", [(4.2, True), (4.4, True), (4.5, False), (4.6, False)])
def test_no_silent_expansion_of_existing_symmetry_acceptance(estimate, accepted):
    if accepted:
        assert sw.declare().analyze(estimate=estimate, ci=(1.0, 7.4)).evidence.estimate == pytest.approx(4.2)
    else:
        with pytest.raises(ValueError, match="not symmetric") as exc:
            sw.declare().analyze(estimate=estimate, ci=(1.0, 7.4))
        assert "acceptance heuristic" in str(exc.value)
        assert "actual printed precision" in str(exc.value) and "unknown" in str(exc.value)


def test_scientific_acceptance_does_not_expand():
    with pytest.raises(ValueError, match="not symmetric") as exc:
        sw.declare().analyze(estimate=4.6e-6, ci=(1e-6, 7.4e-6))
    assert "assumed rounding allowance of 0" in str(exc.value)
    assert "unknown from floats" in str(exc.value)


def test_ratio_scientific_repr_keeps_source_precision_unknown():
    result = sw.declare().analyze(estimate=2.01e-6, ci=(1e-6, 4e-6), ratio=True)
    info, note = result.raw_input["estimate_vs_midpoint"], _difference_note(result)
    assert info["scale"] == "log_ratio"
    assert info["assumed_decimal_places"] is None
    assert info["assumed_rounding_allowance"] == 0.0
    assert info["explained_by_rounding"] is None
    assert "scientific notation" in note and "precision is unknown" in note
    assert info["midpoint"] == pytest.approx(math.log(2e-6))


def test_ratio_input_audit_labels_log_values_and_distinguishes_reconstruction():
    result = sw.declare(units="log rate ratio").analyze(estimate=0.83, ci=(0.75, 0.93), ratio=True)
    info, note = result.raw_input["estimate_vs_midpoint"], _difference_note(result)
    assert result.raw_input["ratio_scale_input"] is True
    assert result.raw_input["estimate"] == 0.83
    assert result.raw_input["ci"] == [0.75, 0.93]
    assert info["scale"] == "log_ratio"
    assert info["given"] == pytest.approx(math.log(0.83))
    assert info["midpoint"] == pytest.approx((math.log(0.75) + math.log(0.93)) / 2)
    assert info["explained_by_rounding"] is None
    assert "estimate given (0.83; ratio scale" in note
    assert "ratio-scale geometric midpoint" in note and "on the log scale" in note
    assert "uses the midpoint, not the given estimate" in note
    assert math.exp(result.evidence.estimate) == pytest.approx(math.sqrt(0.75 * 0.93))
    assert info == json.loads(result.to_json())["raw_input"]["estimate_vs_midpoint"]


@pytest.mark.parametrize("kwargs", [
    dict(estimate=1.0001, ci=(1.00002, 1.00018), ratio=True),
    dict(estimate=4.20000001, ci=(1.0, 7.4)),
])
def test_midpoint_note_preserves_display_distinction_for_close_values(kwargs):
    result = sw.declare().analyze(**kwargs)
    note = _difference_note(result)
    given = re.search(r"estimate given \(([^;)]*)", note).group(1)
    midpoint = re.search(r"interval's midpoint \(([^;)]*)", note).group(1)
    assert float(given) != float(midpoint)
    assert "values rounded for display" in note
    assert note in str(result) and note in result.to_markdown()


@pytest.mark.parametrize("ratio,with_estimate", [(False, True), (False, False), (True, True), (True, False)])
def test_reconstructed_input_level_is_not_confused_with_display_level(ratio, with_estimate):
    ci = (0.75, 0.93) if ratio else (1.0, 7.4)
    estimate = (0.83 if ratio else 4.4) if with_estimate else None
    result = sw.declare(alpha=0.05).analyze(estimate=estimate, ci=ci, ci_level=0.90, ratio=ratio)
    note = _interval_note(result)
    assert "90% input interval" in note and "displayed 95% interval" in note
    assert "recalculated at 1 - alpha" in note and "different level" in note
    assert result.raw_input["ci_level"] == 0.90
    assert result.evidence.zero_level == pytest.approx(0.95)
    lo, hi = (math.log(x) for x in ci) if ratio else ci
    midpoint = (lo + hi) / 2
    se = (hi - lo) / (2 * stats.norm.ppf(0.95))
    assert result.evidence.estimate == pytest.approx(midpoint)
    assert result.evidence.se == pytest.approx(se)
    assert result.evidence.zero_interval == pytest.approx(
        (midpoint - stats.norm.ppf(0.975) * se, midpoint + stats.norm.ppf(0.975) * se)
    )
    assert result.evidence.zero_interval != pytest.approx((lo, hi))


def test_different_levels_are_explained_even_without_a_midpoint_discrepancy():
    result = sw.declare(alpha=0.05).analyze(estimate=4.2, ci=(1.0, 7.4), ci_level=0.90)
    assert "estimate_vs_midpoint" not in result.raw_input
    assert "90% input interval" in _interval_note(result)
    assert "displayed 95% interval" in _interval_note(result)


@pytest.mark.parametrize("ratio", [False, True])
def test_matching_input_and_display_levels_reconstruct_given_interval(ratio):
    ci = (0.75, 0.93) if ratio else (1.0, 7.4)
    estimate = 0.83 if ratio else 4.4
    result = sw.declare(alpha=0.10).analyze(estimate=estimate, ci=ci, ci_level=0.90, df=20, ratio=ratio)
    assert "90% input interval" in _interval_note(result)
    assert "displayed 90% interval" in _interval_note(result)
    assert "same level as the input" in _interval_note(result)
    expected = tuple(math.log(x) for x in ci) if ratio else ci
    assert result.evidence.zero_interval == pytest.approx(expected)
    assert result.evidence.se == pytest.approx((expected[1] - expected[0]) / (2 * stats.t.ppf(0.95, 20)))


def test_exact_midpoint_does_not_create_a_rounding_cause_claim():
    result = sw.declare().analyze(estimate=4.2, ci=(1.0, 7.4))
    assert "estimate_vs_midpoint" not in result.raw_input
    assert not any("rounding" in note.lower() for note in result.raw_input.get("provenance_notes", []))
