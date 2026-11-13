"""Regression coverage for factor claims on explicitly non-natural log scales."""

from dataclasses import replace
import math

import pytest

import statwarrant as sw
from statwarrant.claims import _judge_factor


NON_NATURAL_OR_UNCLEAR = [
    "log base 2 risk ratio",
    "LOG BASE 2 risk ratio",
    "log base2 risk ratio",
    "log base_2 risk ratio",
    "log base_{2} risk ratio",
    "log2 risk ratio",
    "log_2 risk ratio",
    "log_{2} risk ratio",
    "log₂ risk ratio",
    "log 2 risk ratio",
    "log-2 risk ratio",
    "log(2) risk ratio",
    "binary log risk ratio",
    "logarithm base 2 risk ratio",
    "log base 10 risk ratio",
    "log10 risk ratio",
    "log₁₀ risk ratio",
    "log_10 risk ratio",
    "base-10 log risk ratio",
    "base10 log risk ratio",
    "logarithm to base ten of the risk ratio",
    "common log risk ratio",
    "decimal logarithm of the risk ratio",
    "log (decimal) risk ratio",
    "log risk ratio (non-natural)",
    "log risk ratio non-natural",
    "log binary risk ratio",
    "log risk ratio in bits",
    "bits log risk ratio",
    "log risk ratio (base 2)",
    "log risk ratio (base unknown)",
    "log base b risk ratio",
    "log_b risk ratio",
    "log b risk ratio",
    "log^2 risk ratio",
    "log^e risk ratio",
    "lg risk ratio",
    "log base e or 2 risk ratio",
    "log base e (or 2) risk ratio",
    "natural log base 2 risk ratio",
]


def factor(result, sentence):
    out = result.check(sentence, record=False)
    return next(p for p in out.parts if p.rule in ("ratio", "fold"))


@pytest.mark.parametrize("units", NON_NATURAL_OR_UNCLEAR)
@pytest.mark.parametrize("sentence", [
    "The risk of failure halved.",
    "The risk of failure doubled.",
    "The risk differed 2-fold.",
    "The risk differed 10-fold.",
])
def test_explicit_non_natural_or_ambiguous_base_needs_review(units, sentence):
    result = sw.declare(units=units).analyze(estimate=-1, se=0.05)
    part = factor(result, sentence)
    assert part.status == "check"
    assert "base" in part.reason and "by hand" in part.reason
    assert "not compatible" not in part.reason
    assert "0.368" not in part.reason


@pytest.mark.parametrize("units", ["log2 risk ratio", "log_2 risk ratio", "log₂ risk ratio", "lg risk ratio"])
def test_no_baseline_fallback_for_explicit_or_ambiguous_log_notation(units):
    result = sw.declare(units=units).analyze(estimate=-1, se=0.05)
    # Construct the context directly so this remains useful even if the plan later
    # rejects all baselines with log-scale units before a Result can be made.
    context = replace(result.context, baseline=1.0)
    status, reason = _judge_factor(0.5, "halved", context, "the risk halved")
    assert status == "check"
    assert "base" in reason and "relative change" not in reason


@pytest.mark.parametrize("units", ["natural log risk ratio", "ln risk ratio", "log risk ratio",
                                    "log base e risk ratio", "log (base e) risk ratio"])
def test_natural_log_factor_checks_still_use_exp(units):
    result = sw.declare(units=units).analyze(estimate=-1, se=0.05)
    incorrect = factor(result, "The risk of failure halved.")
    compatible = factor(result, "The risk differed 2.7-fold.")
    assert incorrect.status == "conflict" and "0.368" in incorrect.reason
    assert compatible.status == "check" and "0.368" in compatible.reason


def test_natural_log_odds_still_checks_quantity_and_order():
    result = sw.declare(units="log-odds").analyze(estimate=math.log(2), se=0.05)
    assert factor(result, "The odds of failure doubled.").status == "check"
    assert factor(result, "The odds of failure tripled.").status == "conflict"
    mismatch = factor(result, "The risk of failure tripled.")
    assert mismatch.status == "check" and "ratios differ" in mismatch.reason


@pytest.mark.parametrize("units", ["blog visits", "logins per day", "blog risk ratio", "lb"])
def test_non_log_free_text_still_uses_ordinary_baseline(units):
    result = sw.declare(units=units).analyze(estimate=5, se=0.1, baseline=5)
    assert factor(result, "The rate of failure doubled.").status == "check"
    part = factor(result, "The rate of failure tripled.")
    assert part.status == "conflict" and "relative change" in part.reason


def test_an_unsupported_log_notation_does_not_fall_back_to_baseline():
    result = sw.declare(units="log_e risk ratio").analyze(estimate=-1, se=0.05)
    context = replace(result.context, baseline=1.0)
    status, reason = _judge_factor(0.5, "halved", context, "the risk halved")
    assert status == "check" and "by hand" in reason


def test_logit_embedded_in_a_word_is_not_a_log_odds_scale():
    result = sw.declare(units="blogit visits").analyze(estimate=5, se=0.1)
    context = replace(result.context, baseline=5.0)
    status, reason = _judge_factor(3, "tripled", context, "the rate tripled")
    assert status == "conflict" and "relative change" in reason


@pytest.mark.parametrize("units", ["log base 2 risk ratio", "log10 risk ratio", "natural log risk ratio"])
def test_raw_scale_numerical_inference_is_unchanged(units):
    result = sw.declare(units=units).analyze(estimate=-1, se=0.05)
    assert result.evidence.estimate == pytest.approx(-1)
    assert result.evidence.se == pytest.approx(0.05)
    assert result.evidence.zero_interval == pytest.approx((-1.0979981992270027, -0.9020018007729973))
    right = result.check("The estimate was -1.0.", record=False)
    wrong = result.check("The estimate was -3.0.", record=False)
    assert next(p for p in right.parts if p.rule == "reported-number").status == "consistent"
    assert next(p for p in wrong.parts if p.rule == "reported-number").status == "conflict"


def test_other_conflicts_are_not_suppressed_by_the_factor_guard():
    result = sw.declare(units="log base 2 risk ratio").analyze(estimate=-1, se=0.05)
    out = result.check("The risk of failure halved. The estimate was -3.0.", record=False)
    assert next(p for p in out.parts if p.rule == "ratio").status == "check"
    assert next(p for p in out.parts if p.rule == "reported-number").status == "conflict"
    assert out.level == "conflict"


def test_ratio_input_uses_natural_log_even_with_conflicting_declared_units():
    try:
        result = sw.declare(units="log base 2 risk ratio").analyze(ci=(0.45, 0.55), ratio=True)
    except ValueError:
        # Rejecting this contradictory declaration is also a safe outcome.
        return
    assert result.evidence.estimate == pytest.approx((math.log(0.45) + math.log(0.55)) / 2)
    assert result.raw_input["ratio_scale_input"] is True
    part = factor(result, "The risk of failure halved.")
    # The units contradict the computation, so the linter must not decide which
    # account is authoritative even though ratio=True internally uses ln.
    assert part.status == "check" and "base" in part.reason
