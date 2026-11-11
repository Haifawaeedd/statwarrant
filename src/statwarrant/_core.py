"""Core inference: difference from zero, equivalence (TOST) and minimal effect (MET).

Every decision is read from a confidence interval. The interval policy decides
which interval each decision uses:

* ``"single"`` (default): one (1 - alpha) interval for every decision. The two
  one-sided tests behind equivalence and minimal-effect claims then run at
  alpha / 2 per side. One picture, no contradictions, slightly less power.
* ``"standard"``: the zero test uses the (1 - alpha) interval and the
  equivalence / minimal-effect tests use the (1 - 2 alpha) interval, as in
  Schuirmann's TOST and the TOSTER package. The two levels can disagree; when
  they do, the result says so explicitly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from scipy import stats

POLICIES = ("single", "standard")


def _dist(df: Optional[float]):
    """Reference distribution: Student t with ``df`` degrees of freedom, or normal."""
    if df is None or math.isinf(df):
        return stats.norm
    if df <= 0:
        raise ValueError(f"df must be positive, got {df!r}")
    return stats.t(df)


def critical_value(two_sided_level: float, df: Optional[float]) -> float:
    """Critical value for a two-sided interval at ``two_sided_level`` (e.g. 0.95)."""
    if not 0 < two_sided_level < 1:
        raise ValueError("interval level must be between 0 and 1")
    return float(_dist(df).ppf(0.5 + two_sided_level / 2))


def interval(estimate: float, se: float, level: float, df: Optional[float]) -> Tuple[float, float]:
    c = critical_value(level, df)
    return (estimate - c * se, estimate + c * se)


@dataclass(frozen=True)
class Evidence:
    """What the data say about the effect, under the declared plan.

    Attributes are plain numbers and booleans so the object can be serialised
    and tested. ``claim_class`` is the label the claim contract is built on.
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

    bounds_level: Optional[float]
    bounds_interval: Optional[Tuple[float, float]]
    bounds_threshold: Optional[float]
    p_equivalence: Optional[float]
    p_minimal_effect: Optional[float]
    equivalent: Optional[bool]
    exceeds_sesoi: Optional[bool]

    claim_class: str
    level_conflict: bool

    @property
    def direction(self) -> int:
        """+1, -1 or 0 when the sign of the effect is established."""
        lo, hi = self.zero_interval
        if self.exceeds_sesoi and self.bounds_interval is not None:
            return 1 if self.bounds_interval[0] > 0 else -1
        if lo > 0:
            return 1
        if hi < 0:
            return -1
        return 0

    def to_dict(self) -> dict:
        return {
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
            "bounds_tests": None
            if self.sesoi is None
            else {
                "interval_level": self.bounds_level,
                "interval": list(self.bounds_interval),
                "per_side_threshold": self.bounds_threshold,
                "p_equivalence": self.p_equivalence,
                "p_minimal_effect": self.p_minimal_effect,
                "equivalent": self.equivalent,
                "exceeds_sesoi": self.exceeds_sesoi,
            },
            "claim_class": self.claim_class,
            "level_conflict": self.level_conflict,
        }


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
    if not 0 < alpha < 0.5:
        raise ValueError("alpha must be between 0 and 0.5")

    dist = _dist(df)
    zero_level = 1 - alpha
    zero_iv = interval(estimate, se, zero_level, df)
    p_zero = float(2 * dist.sf(abs(estimate) / se))
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
            None, None, None, None, None, None, None,
            cls, False,
        )

    low, high = sesoi
    threshold = alpha / 2 if policy == "single" else alpha
    bounds_level = 1 - 2 * threshold
    biv = interval(estimate, se, bounds_level, df)

    # Equivalence (TOST): reject both H0: theta <= low and H0: theta >= high.
    p_eq = float(max(dist.sf((estimate - low) / se), dist.cdf((estimate - high) / se)))
    # Minimal effect (MET): reject H0: low <= theta <= high in either direction.
    p_met = float(min(dist.sf((estimate - high) / se), dist.cdf((estimate - low) / se)))

    equivalent = low < biv[0] and biv[1] < high
    met_pos = biv[0] > high
    met_neg = biv[1] < low
    exceeds = met_pos or met_neg

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
    elif biv[0] < low and biv[1] > high:
        cls = "inconclusive_both"
    else:
        cls = "inconclusive_one_side"

    # A minimal effect established at one level while the zero test fails at
    # another: only possible under the "standard" policy.
    conflict = exceeds and not differs

    return Evidence(
        estimate, se, df, alpha, policy, (low, high),
        zero_level, zero_iv, p_zero, differs,
        bounds_level, biv, threshold, p_eq, p_met, equivalent, exceeds,
        cls, conflict,
    )
