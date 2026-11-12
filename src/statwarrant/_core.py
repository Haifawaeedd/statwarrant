"""Core inference: difference from zero, equivalence (TOST) and minimal effect (MET).

Every decision is read from a confidence interval.

* Zero test: the (1 - alpha) interval excludes zero.
* Minimal-effect test (MET): the (1 - alpha) interval lies entirely beyond one of
  the SESOI bounds. The test can succeed in either direction, so alpha is split
  across the two directions (alpha / 2 per side). This keeps the type I error at
  or below alpha for every true effect inside the bounds, under both policies.
* Equivalence test (TOST, Schuirmann 1987): the interval lies entirely inside
  the SESOI bounds. Both one-sided tests must reject (an intersection-union
  test), so each may run at the full per-side level. The interval policy
  decides which level:

  - ``"single"`` (default): alpha / 2 per side, i.e. the same (1 - alpha)
    interval as every other decision. One picture, no contradictions,
    slightly less power for equivalence.
  - ``"standard"``: alpha per side, i.e. the (1 - 2 alpha) interval, as in
    Schuirmann's TOST and the TOSTER package. When equivalence is established
    with that interval but the (1 - alpha) interval reaches outside the bounds,
    the result reports a level conflict.

Version 0.1.0 also ran the minimal-effect test at alpha per side under
``"standard"``; its type I error could then approach 2 alpha. That was removed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from scipy import stats

POLICIES = ("single", "standard")
MIN_ALPHA = 1e-10


def level_text(level: float) -> str:
    """An interval level as a percentage with the digits it needs (95%, 99.9%, 99.99999%)."""
    return f"{level * 100:.10g}%"


def _dist(df: Optional[float]):
    """Reference distribution: Student t with ``df`` degrees of freedom, or normal."""
    if df is None:
        return stats.norm
    try:
        df = float(df)
    except (TypeError, ValueError):
        raise ValueError(f"df must be a positive number or None, got {df!r}") from None
    if math.isnan(df):
        raise ValueError("df must be a positive number or None, got nan")
    if math.isinf(df) and df > 0:
        return stats.norm
    if not df > 0:
        raise ValueError(f"df must be positive, got {df!r}")
    return stats.t(df)


def critical_value(two_sided_level: float, df: Optional[float]) -> float:
    """Critical value for a two-sided interval at ``two_sided_level`` (e.g. 0.95)."""
    if not 0 < two_sided_level < 1:
        raise ValueError("interval level must be between 0 and 1")
    return float(_dist(df).isf((1 - two_sided_level) / 2))


def interval(estimate: float, se: float, level: float, df: Optional[float]) -> Tuple[float, float]:
    c = critical_value(level, df)
    return (estimate - c * se, estimate + c * se)


def _interval_tail(estimate: float, se: float, tail: float, df: Optional[float]) -> Tuple[float, float]:
    """Interval whose two tails each hold ``tail``; uses the survival function, stable for tiny alpha."""
    c = float(_dist(df).isf(tail))
    return (estimate - c * se, estimate + c * se)


@dataclass(frozen=True)
class Thresholds:
    """The decision for every symmetric threshold (-d, d) at once.

    Both tests are read from intervals, so the whole sensitivity to the choice of
    threshold is fixed by two numbers:

    * ``met_below``: an effect beyond +/-d is established for every d below this
      value (the end of the (1 - alpha) interval nearest zero); None when that
      interval contains zero.
    * ``equivalence_above``: equivalence within +/-d is established for every d
      above this value (the end of the equivalence interval farthest from zero).

    Both cut-offs are strict: at exactly ``met_below`` or ``equivalence_above`` the
    decision is "undetermined". For thresholds in between, neither is established. This re-reads the same
    intervals; it is not a family of new tests, and choosing a threshold after
    seeing these numbers is not a confirmatory claim.
    """

    met_below: Optional[float]
    met_level: float
    equivalence_above: float
    equivalence_level: float

    def decision(self, d: float) -> str:
        """"exceeds", "equivalent" or "undetermined" for the symmetric threshold (-d, d)."""
        if not (math.isfinite(d) and d > 0):
            raise ValueError("a threshold must be a finite positive number")
        if self.met_below is not None and d < self.met_below:
            return "exceeds"
        if d > self.equivalence_above:
            return "equivalent"
        return "undetermined"

    def to_dict(self) -> dict:
        return {
            "met_below": self.met_below,
            "met_interval_level": self.met_level,
            "equivalence_above": self.equivalence_above,
            "equivalence_interval_level": self.equivalence_level,
        }


@dataclass(frozen=True)
class Evidence:
    """What the data say about the effect, under the declared plan.

    Attributes are plain numbers and booleans so the object can be serialised
    and tested. ``claim_class`` is the label the claim contract is built on.
    p-values for the equivalence and minimal-effect tests are one-sided and are
    compared with the per-side thresholds reported next to them.
    """

    estimate: float
    se: float
    df: Optional[float]
    alpha: float
    policy: str
    sesoi: Optional[Tuple[float, float]]

    zero_level: float
    zero_interval: Tuple[float, float]
    p_zero: float
    differs_from_zero: bool

    equivalence_level: Optional[float]
    equivalence_interval: Optional[Tuple[float, float]]
    equivalence_threshold: Optional[float]
    p_equivalence: Optional[float]
    equivalent: Optional[bool]

    met_level: Optional[float]
    met_interval: Optional[Tuple[float, float]]
    met_threshold: Optional[float]
    p_minimal_effect: Optional[float]
    exceeds_sesoi: Optional[bool]

    claim_class: str
    level_conflict: bool

    def thresholds(self) -> Thresholds:
        """Decisions for every symmetric threshold at once (see :class:`Thresholds`)."""
        lo, hi = self.zero_interval
        met_below = min(abs(lo), abs(hi)) if (lo > 0 or hi < 0) else None
        eq_tail = self.alpha / 2 if self.policy == "single" else self.alpha
        eq_level = 1 - 2 * eq_tail
        elo, ehi = _interval_tail(self.estimate, self.se, eq_tail, self.df)
        return Thresholds(met_below, self.zero_level, max(abs(elo), abs(ehi)), eq_level)

    @property
    def direction(self) -> int:
        """+1 or -1 when the (1 - alpha) interval excludes zero, otherwise 0."""
        lo, hi = self.zero_interval
        if lo > 0:
            return 1
        if hi < 0:
            return -1
        return 0

    def to_dict(self) -> dict:
        out = {
            "estimate": self.estimate,
            "se": self.se,
            "df": self.df,
            "alpha": self.alpha,
            "interval_policy": self.policy,
            "sesoi": list(self.sesoi) if self.sesoi else None,
            "zero_test": {
                "interval_level": self.zero_level,
                "interval": list(self.zero_interval),
                "p_value": self.p_zero,
                "differs_from_zero": self.differs_from_zero,
            },
            "equivalence_test": None,
            "minimal_effect_test": None,
            "claim_class": self.claim_class,
            "level_conflict": self.level_conflict,
        }
        if self.sesoi is not None:
            out["equivalence_test"] = {
                "interval_level": self.equivalence_level,
                "interval": list(self.equivalence_interval),
                "per_side_threshold": self.equivalence_threshold,
                "p_value": self.p_equivalence,
                "equivalent": self.equivalent,
            }
            out["minimal_effect_test"] = {
                "interval_level": self.met_level,
                "interval": list(self.met_interval),
                "per_side_threshold": self.met_threshold,
                "p_value": self.p_minimal_effect,
                "exceeds_sesoi": self.exceeds_sesoi,
            }
        return out


def evaluate(
    estimate: float,
    se: float,
    df: Optional[float],
    alpha: float,
    policy: str,
    sesoi: Optional[Tuple[float, float]],
) -> Evidence:
    """Run the three tests and classify the result."""
    if policy not in POLICIES:
        raise ValueError(f"interval_policy must be one of {POLICIES}, got {policy!r}")
    if not (math.isfinite(estimate) and math.isfinite(se)):
        raise ValueError("estimate and se must be finite numbers")
    if se <= 0:
        raise ValueError("se must be strictly positive")
    if not MIN_ALPHA <= alpha < 0.5:
        raise ValueError(f"alpha must be at least {MIN_ALPHA:g} and below 0.5")
    if df is not None and math.isinf(float(df)) and float(df) > 0:
        df = None  # infinite degrees of freedom: the normal reference
    if sesoi is not None:
        low, high = sesoi
        if not (math.isfinite(low) and math.isfinite(high) and low < 0 < high):
            raise ValueError("sesoi bounds must be finite with low < 0 < high")

    dist = _dist(df)
    zero_level = 1 - alpha
    zero_iv = _interval_tail(estimate, se, alpha / 2, df)
    p_zero = float(min(1.0, 2 * dist.sf(abs(estimate) / se)))
    differs = zero_iv[0] > 0 or zero_iv[1] < 0

    if sesoi is None:
        if zero_iv[0] > 0:
            cls = "differs_positive"
        elif zero_iv[1] < 0:
            cls = "differs_negative"
        else:
            cls = "inconclusive_no_sesoi"
        return Evidence(
            estimate, se, df, alpha, policy, None,
            zero_level, zero_iv, p_zero, differs,
            None, None, None, None, None,
            None, None, None, None, None,
            cls, False,
        )

    low, high = sesoi

    # Equivalence (TOST): reject both H0: theta <= low and H0: theta >= high.
    eq_threshold = alpha / 2 if policy == "single" else alpha
    eq_level = 1 - 2 * eq_threshold
    eq_iv = _interval_tail(estimate, se, eq_threshold, df)
    p_eq = float(max(dist.sf((estimate - low) / se), dist.cdf((estimate - high) / se)))
    equivalent = low < eq_iv[0] and eq_iv[1] < high

    # Minimal effect (MET): reject H0: low <= theta <= high in either direction,
    # alpha / 2 per direction, i.e. the (1 - alpha) interval beyond a bound.
    met_threshold = alpha / 2
    met_level = 1 - alpha
    met_iv = zero_iv
    p_met = float(min(dist.sf((estimate - high) / se), dist.cdf((estimate - low) / se)))
    met_pos = met_iv[0] > high
    met_neg = met_iv[1] < low
    exceeds = met_pos or met_neg

    # Wording only: an interval that passes a bound by floating-point noise
    # (e.g. ppf versus isf in the last digit) touches it rather than extends beyond it.
    # Each side uses its own scale, so a huge lower bound cannot hide an upper crossing.
    past_low = zero_iv[0] < low - 1e-12 * max(abs(low), se)
    past_high = zero_iv[1] > high + 1e-12 * max(abs(high), se)
    if met_pos:
        cls = "exceeds_sesoi_positive"
    elif met_neg:
        cls = "exceeds_sesoi_negative"
    elif equivalent and differs:
        cls = "nonzero_negligible"
    elif equivalent:
        cls = "equivalent"
    elif differs and zero_iv[0] > 0:
        cls = "positive_importance_undetermined"
    elif differs:
        cls = "negative_importance_undetermined"
    elif past_low and past_high:
        cls = "inconclusive_both"
    elif past_low or past_high:
        cls = "inconclusive_one_side"
    else:
        # The interval touches a bound without extending beyond it.
        cls = "inconclusive_at_bound"

    # Only under "standard": equivalence read from the (1 - 2 alpha) interval
    # while the (1 - alpha) interval reaches outside the bounds.
    conflict = bool(equivalent and not (low < zero_iv[0] and zero_iv[1] < high))

    return Evidence(
        estimate, se, df, alpha, policy, (low, high),
        zero_level, zero_iv, p_zero, differs,
        eq_level, eq_iv, eq_threshold, p_eq, equivalent,
        met_level, met_iv, met_threshold, p_met, exceeds,
        cls, conflict,
    )
