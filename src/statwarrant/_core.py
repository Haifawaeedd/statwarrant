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
import struct
import sys
import warnings
from dataclasses import dataclass, field, replace
from typing import Optional, Tuple

from scipy import integrate, special, stats

from ._precision import checked_float

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


def _log_t_tail(x: float, df: float) -> float:
    """Log one-sided Student t tail, including when SciPy's sf/logsf underflow.

    Integrate the density on a log-distance scale, factoring out its value at x.
    This avoids forming x*x, the tiny tail, or a huge unscaled integral. It is
    used only in the subnormal/zero tail region, not for ordinary decisions.
    """
    if not (math.isfinite(x) and x > 1 and math.isfinite(df) and df > 0):
        return -math.inf
    try:
        ratio = math.sqrt(df) / x
        w = 1.0 / (1.0 + ratio * ratio)
        k = (df + 1.0) * w - 1.0
        if not (0 < w <= 1 and math.isfinite(k) and k > 0):
            return -math.inf
        r = 2 * math.log(x) - math.log(df)
        log1pr = math.log1p(math.exp(r)) if r < 0 else r + math.log1p(math.exp(-r))
        logpdf = -math.log(df) / 2 - float(special.betaln(0.5, df / 2)) - (df / 2 + 0.5) * log1pr

        def integrand(u):
            v = u / k
            if v < 300:
                delta = math.log1p(w * math.expm1(2 * v))
            else:
                delta = 2 * v + math.log(w + (1 - w) * math.exp(-2 * v))
            exponent = v - (df / 2 + 0.5) * delta
            return math.exp(exponent) if exponent > -746 else 0.0

        with warnings.catch_warnings():
            warnings.simplefilter("error", integrate.IntegrationWarning)
            integral, error = integrate.quad(integrand, 0, math.inf, epsabs=1e-11, epsrel=1e-11, limit=150)
        if not (math.isfinite(integral) and integral > 0 and error <= 1e-9 * integral):
            return -math.inf
        result = logpdf + math.log(x) - math.log(k) + math.log(integral)
        return result if math.isfinite(result) and result <= 0 else -math.inf
    except (ArithmeticError, ValueError, integrate.IntegrationWarning):
        return -math.inf


def _log_tail(dist, x: float, df: Optional[float]) -> float:
    """Log sf, with a fallback where SciPy's Student t logsf loses the tail."""
    log_sf = float(dist.logsf(x))
    if df is not None and (not math.isfinite(log_sf) or log_sf < math.log(sys.float_info.min)):
        recovered = _log_t_tail(x, df)
        if math.isfinite(recovered):
            return recovered
    return log_sf


def _tail_p(dist, x: float, df: Optional[float], two_sided: bool = False) -> float:
    """Use ordinary sf except in the extreme tail; multiply on the log scale there."""
    sf = float(dist.sf(x))
    if sf >= sys.float_info.min:
        return min(1.0, sf * (2 if two_sided else 1))
    log_sf = _log_tail(dist, x, df)
    if math.isfinite(log_sf):
        return min(1.0, math.exp(log_sf + (math.log(2.0) if two_sided else 0.0)))
    # The log tail may itself be unavailable; retain any nonzero SciPy result.
    return min(1.0, sf * (2 if two_sided else 1))


def _critical_from_tail(tail: float, df: Optional[float]) -> float:
    """Refuse a critical value if the distribution cannot invert its own tail.

    Some SciPy versions return a finite but grossly inaccurate Student-t isf
    for extraordinarily small df. A self-consistency check prevents reporting
    an inference based on that result; it is not proof of general accuracy.
    """
    dist = _dist(df)
    c = float(dist.isf(tail))
    if not math.isfinite(c) or c < 0:
        raise ValueError("the reference distribution's critical value is not finite; check df and alpha")
    observed_tail = float(dist.sf(c))
    if not math.isfinite(observed_tail) or not math.isclose(observed_tail, tail, rel_tol=1e-6, abs_tol=0.0):
        raise ValueError("the reference distribution's critical value cannot be verified for this df and alpha")
    return c


def critical_value(two_sided_level: float, df: Optional[float]) -> float:
    """Critical value for a two-sided interval at ``two_sided_level`` (e.g. 0.95)."""
    if not 0 < two_sided_level < 1:
        raise ValueError("interval level must be between 0 and 1")
    return _critical_from_tail((1 - two_sided_level) / 2, df)


def interval(estimate: float, se: float, level: float, df: Optional[float]) -> Tuple[float, float]:
    c = critical_value(level, df)
    return (estimate - c * se, estimate + c * se)


def _interval_tail(estimate: float, se: float, tail: float, df: Optional[float]) -> Tuple[float, float]:
    """Interval whose two tails each hold ``tail``; uses the survival function, stable for tiny alpha."""
    c = _critical_from_tail(tail, df)
    return (estimate - c * se, estimate + c * se)


@dataclass(frozen=True)
class Thresholds:
    """The decision for every symmetric threshold (-d, d) at once.

    Both tests are read from intervals, so the whole sensitivity to the choice of
    threshold is fixed by two numbers:

    * ``met_below``: an effect beyond +/-d is established for every positive
      representable d below this value; None when the zero test is not established.
    * ``equivalence_above``: equivalence within +/-d is established for every d
      above this value, among positive finite representable thresholds.

    Both cut-offs are strict: at a positive finite cut-off the decision is
    "undetermined", and between the cut-offs neither is established. At the
    domain limits the open side can be empty: ``met_below`` can be the smallest
    positive float, or ``equivalence_above`` the largest finite float. Conversely,
    ``equivalence_above`` can be zero if all positive finite floats are equivalent;
    zero is not itself a valid input to :meth:`decision`. This re-reads the same
    intervals; it is not a family of new tests, and choosing a threshold after
    seeing these numbers is not a confirmatory claim.
    """

    met_below: Optional[float]
    met_level: float
    equivalence_above: float
    equivalence_level: float
    # The same arithmetic as evaluate(), so decision(d) always agrees with it
    estimate: float = field(default=0.0, repr=False)
    se: float = field(default=1.0, repr=False)
    met_critical: float = field(default=math.inf, repr=False)
    equivalence_critical: float = field(default=math.inf, repr=False)

    def decision(self, d: float) -> str:
        """"exceeds", "equivalent" or "undetermined" for the symmetric threshold (-d, d).

        Computed like evaluate(): the bound is subtracted from the estimate before
        dividing by the standard error, which keeps precision near a cut-off.
        """
        d = checked_float(d, "threshold")
        if not (math.isfinite(d) and d > 0):
            raise ValueError("a threshold must be a finite positive number")
        if (abs(self.estimate) - d) / self.se > self.met_critical:
            return "exceeds"
        if (d - abs(self.estimate)) / self.se > self.equivalence_critical:
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
        met_below = min(abs(lo), abs(hi)) if self.differs_from_zero else None
        eq_tail = self.alpha / 2 if self.policy == "single" else self.alpha
        eq_level = 1 - 2 * eq_tail
        elo, ehi = _interval_tail(self.estimate, self.se, eq_tail, self.df)
        th = Thresholds(met_below, self.zero_level, max(abs(elo), abs(ehi)), eq_level,
                        self.estimate, self.se, _critical_from_tail(self.alpha / 2, self.df),
                        _critical_from_tail(eq_tail, self.df))
        # Interval and test-statistic arithmetic can diverge by many floats near
        # cancellation. Find the exact transitions of decision(), not just nearby
        # interval endpoints, so the printed cut-offs cannot contradict it.
        return replace(th, met_below=None if met_below is None else _edge(th, met_below, "exceeds", below=True),
                       equivalence_above=_edge(th, th.equivalence_above, "equivalent", below=False))

    @property
    def direction(self) -> int:
        """+1 or -1 when the difference from zero is established, otherwise 0."""
        if not self.differs_from_zero:
            return 0
        return 1 if self.estimate > 0 else -1

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
        if self.p_zero == 0.0:
            out["zero_test"]["p_value_underflow_or_unavailable"] = True
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
            if self.p_equivalence == 0.0:
                out["equivalence_test"]["p_value_underflow_or_unavailable"] = True
            if self.p_minimal_effect == 0.0:
                out["minimal_effect_test"]["p_value_underflow_or_unavailable"] = True
        return out


_MAX_FINITE_BITS = 0x7FEFFFFFFFFFFFFF


def _positive_float(bits: int) -> float:
    """Decode a nonnegative finite IEEE-754 binary64 by its ordered bit pattern."""
    return struct.unpack(">d", struct.pack(">Q", bits))[0]


def _edge(th: "Thresholds", start: float, label: str, below: bool) -> float:
    """Find the strict boundary on the positive finite binary64 domain.

    For MET, the labelled region is a prefix; return its first non-labelled
    float. For equivalence, the labelled region is a suffix; return its last
    non-labelled float. Rounded subtraction and division by a positive SE are
    monotone, so both predicates are monotone on this domain. A zero sentinel
    represents an empty non-labelled prefix; the largest finite float represents
    an empty labelled suffix. No decision is ever requested for zero or infinity.
    """
    # Most interval-derived guesses are already adjacent to the transition.
    # Check the invariant, rather than assuming a small rounding discrepancy.
    if math.isfinite(start) and start >= 0:
        if start > 0 and th.decision(start) == label:
            candidate = math.nextafter(start, math.inf if below else 0.0)
            if candidate == 0.0 and not below:
                return 0.0
            if math.isfinite(candidate) and candidate > 0 and th.decision(candidate) != label:
                return candidate
        elif start > 0 or not below:
            neighbor = math.nextafter(start, 0.0 if below else math.inf)
            if (below and neighbor == 0.0) or (not below and not math.isfinite(neighbor)):
                return start
            if neighbor > 0 and math.isfinite(neighbor) and th.decision(neighbor) == label:
                return start

    # Nonnegative binary64 encodings have the same order as their values. For
    # MET, lo is labelled (or the zero sentinel), and hi is not labelled: max
    # is never labelled because abs(estimate) <= max. For equivalence, lo is
    # unlabelled (or zero), and hi is labelled (or the MAX+1 sentinel). The
    # sentinels are never passed to decision. Each iteration maintains those
    # invariants and halves an integer range smaller than 2**63; 63 suffice.
    lo, hi = (0, _MAX_FINITE_BITS) if below else (0, _MAX_FINITE_BITS + 1)
    for _ in range(63):
        if hi - lo == 1:
            return _positive_float(hi if below else lo)
        mid = (lo + hi) // 2
        is_labelled = th.decision(_positive_float(mid)) == label
        if is_labelled == below:
            lo = mid
        else:
            hi = mid
    if hi - lo == 1:
        return _positive_float(hi if below else lo)
    raise RuntimeError("could not establish a finite threshold boundary")


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
    estimate = checked_float(estimate, "estimate")
    se = checked_float(se, "se")
    df = None if df is None else checked_float(df, "df")
    if sesoi is not None:
        low, high = sesoi
        sesoi = (checked_float(low, "sesoi lower bound"), checked_float(high, "sesoi upper bound"))
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

    # Every decision is made from a test statistic in which the bound is subtracted
    # before dividing by the standard error; intervals are for reporting. This keeps a
    # decision and its p-value in agreement even when estimate and bound are large and close.
    dist = _dist(df)
    zero_level = 1 - alpha
    c_zero = _critical_from_tail(alpha / 2, df)
    zero_iv = _interval_tail(estimate, se, alpha / 2, df)
    p_zero = _tail_p(dist, abs(estimate) / se, df, two_sided=True)
    differs = abs(estimate) / se > c_zero
    if not all(math.isfinite(v) for v in zero_iv):
        raise ValueError("the estimate or standard error is too large for floating point; rescale the outcome")

    if sesoi is None:
        if differs and estimate > 0:
            cls = "differs_positive"
        elif differs:
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
    c_eq = _critical_from_tail(eq_threshold, df)
    z_low, z_high = (estimate - low) / se, (high - estimate) / se
    if not (math.isfinite(z_low) and math.isfinite(z_high) and all(math.isfinite(v) for v in eq_iv)):
        raise ValueError("the inputs are too large for floating point; rescale the outcome and the SESOI")
    p_eq = max(_tail_p(dist, z_low, df), _tail_p(dist, z_high, df))
    equivalent = z_low > c_eq and z_high > c_eq

    # Minimal effect (MET): reject H0: low <= theta <= high in either direction,
    # alpha / 2 per direction, i.e. the (1 - alpha) interval beyond a bound.
    met_threshold = alpha / 2
    met_level = 1 - alpha
    met_iv = zero_iv
    p_met = min(_tail_p(dist, -z_high, df), _tail_p(dist, -z_low, df))
    met_pos = -z_high > c_zero
    met_neg = -z_low > c_zero
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
    elif differs and estimate > 0:
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
    conflict = bool(equivalent and not (z_low > c_zero and z_high > c_zero))

    return Evidence(
        estimate, se, df, alpha, policy, (low, high),
        zero_level, zero_iv, p_zero, differs,
        eq_level, eq_iv, eq_threshold, p_eq, equivalent,
        met_level, met_iv, met_threshold, p_met, exceeds,
        cls, conflict,
    )
