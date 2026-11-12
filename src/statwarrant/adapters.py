"""Turn common Python outputs into (estimate, standard error, degrees of freedom).

Every adapter checks its own work: after extracting the numbers it recomputes the
two-sided p-value with statwarrant's reference distribution and compares it with
the p-value the original object reports. If they disagree, the adapter raises
instead of interpreting a different test from the one that was run.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Optional, Sequence, Tuple

import numpy as np

from ._core import _dist, _log_tail, _tail_p, critical_value

Triple = Tuple[float, float, Optional[float]]


class AdapterMismatch(ValueError):
    """statwarrant could not reproduce the p-value reported by the original result."""


def _p_two_sided(est: float, se: float, df: Optional[float]) -> float:
    return _tail_p(_dist(df), abs(est) / se, df, two_sided=True)


def _scalar(x) -> Optional[float]:
    try:
        v = float(np.asarray(x).item())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _verify(est: float, se: float, df: Optional[float], reported_stat, reported_p, what: str) -> Optional[str]:
    """Stop unless statwarrant reproduces the original test statistic and p-value.

    Tiny positive p-values are compared using the reference distribution's log tail.
    An exact source zero cannot be verified as a p-value, even when the statistic agrees.
    """
    advice = "Rather than interpret a different test, statwarrant stops here. Pass estimate=, se= and df= explicitly."
    stat, p = _scalar(reported_stat), _scalar(reported_p)
    if stat is None or p is None:
        raise AdapterMismatch(f"{what} does not report a finite test statistic and p-value, so statwarrant cannot "
                              f"check that it reads the same test. {advice}")
    if p == 0.0:
        # Do not turn a positive or negative extended-precision probability into
        # a purported source zero when narrowing it to the public float format.
        try:
            original_p = np.asarray(reported_p).item()
            if isinstance(original_p, str):
                original_p = Decimal(original_p)
            nonzero_before_conversion = original_p > 0 or original_p < 0
        except (InvalidOperation, TypeError, ValueError):
            nonzero_before_conversion = False
        if nonzero_before_conversion:
            raise AdapterMismatch(f"{what} reports a nonzero p-value that cannot be represented as a float, "
                                  f"so statwarrant cannot verify it. {advice}")
    if not 0.0 <= p <= 1.0:
        raise AdapterMismatch(f"{what} reports p = {p!r}, which is not a probability. {advice}")
    mine_stat = est / se
    if not math.isclose(mine_stat, stat, rel_tol=1e-6, abs_tol=1e-9):
        raise AdapterMismatch(f"statwarrant reads {what} as estimate {est:.6g} and SE {se:.6g} (statistic "
                              f"{mine_stat:.6g}), but the result reports statistic {stat:.6g}. {advice}")
    mine_p = _p_two_sided(est, se, df)
    if p == 0.0:
        # Some implementations lose tiny tails to underflow or 1 - CDF cancellation.
        # Retain compatibility only for tails near floating-point precision or smaller;
        # a zero with an ordinary p is an unmistakable mismatch.
        if mine_p > 1e-15:
            raise AdapterMismatch(f"{what} reports p = 0, but statwarrant computes p = {mine_p:.6g}. {advice}")
        computed = (f"p = {mine_p:.3g}" if mine_p else
                    "a p-value that underflowed or is unavailable (not an exact zero)")
        return (f"{what} reports p = 0, which could reflect numerical underflow or loss of precision, "
                f"or an error or different computation. The p-value could not be verified; "
                f"statwarrant computes {computed}.")
    # Use logsf directly, not log(sf): sf can underflow while logsf remains finite.
    if max(mine_p, p) <= 1e-250:
        log_p = math.log(p)
        log_mine = math.log(2.0) + _log_tail(_dist(df), abs(est) / se, df)
        if not math.isfinite(log_mine):
            return (f"{what} reports p = {p:.3g}, but the reference log-tail could not be computed; "
                    "the reported p-value is unverified even though the statistic agrees.")
        # A subnormal value can have substantial rounding error. Compare with its
        # round-to-nearest bin as well as the existing logarithmic tolerance.
        half_ulp_ratio = (math.ulp(p) / p) / 2
        lower = log_p + math.log1p(-half_ulp_ratio)
        upper = log_p + math.log1p(half_ulp_ratio)
        tol = 1e-6 * max(abs(log_p), abs(log_mine))
        disagree = log_mine < lower - tol or log_mine > upper + tol
    else:
        disagree = not math.isclose(mine_p, p, rel_tol=1e-6, abs_tol=0.0)
    if disagree:
        computed = f"p = {mine_p:.6g}" if mine_p else "an underflowed or unavailable p-value (not exact zero)"
        raise AdapterMismatch(
            f"statwarrant reads {what} with {'a normal reference' if df is None else f'df {df:.6g}'}, giving "
            f"{computed}, but the result reports p = {p:.6g}. {advice}"
        )
    if mine_p == 0.0:
        return (f"{what} reports p = {p:.3g}; its agreement was checked using the reference log tail, "
                "but statwarrant's ordinary floating-point p-value underflows to 0.")
    return None


_EPS = float(np.finfo(float).eps)
# Largest relative error in a standard error recovered from interval endpoints that
# statwarrant accepts.
MAX_RECONSTRUCTION_ERROR = 1e-6


def _source_epsilon(*values) -> float:
    """Use at least binary64 epsilon, or the coarsest floating dtype in the source."""
    eps = _EPS
    for value in values:
        try:
            dtype = np.asarray(value).dtype
            if np.issubdtype(dtype, np.floating):
                eps = max(eps, float(np.finfo(dtype).eps))
        except (TypeError, ValueError):
            continue
    return eps


def _reconstruction_error(lo: float, hi: float, eps: float = _EPS) -> float:
    """Bound on the relative error of (hi - lo) when each endpoint carries rounding error.

    Endpoints far from zero relative to the interval's width (e.g. 1e14 +/- 0.3) lose
    most of their significant digits on subtraction.
    """
    return 4 * eps * max(abs(lo), abs(hi)) / (hi - lo)


def from_ci(lo: float, hi: float, level: float = 0.95, df: Optional[float] = None) -> Tuple[float, float]:
    """Midpoint and standard error implied by a symmetric two-sided interval.

    Endpoints alone cannot show that the original interval was symmetric around its
    estimate: statwarrant assumes it was (a Wald-type interval).
    """
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        raise ValueError("the interval must be finite with lower < upper (two-sided intervals only)")
    err = _reconstruction_error(lo, hi)
    if err > MAX_RECONSTRUCTION_ERROR:
        raise ValueError(
            f"the interval ({lo!r}, {hi!r}) is too narrow for its distance from zero: its width can only be "
            f"recovered to a relative error of about {err:.1g}. Pass estimate= and se= directly, or analyse "
            f"differences from a nearby reference value."
        )
    se = (hi - lo) / (2 * critical_value(level, df))
    return (lo + hi) / 2, se


def from_scipy(result, notes: Optional[list] = None) -> Tuple[float, float, Optional[float], Optional[float]]:
    """scipy.stats t-test results (ttest_ind, ttest_rel, ttest_1samp).

    Returns (estimate, se, df, null), where null may be unknown. The estimate is the difference the test
    tested: for ``ttest_1samp(x, popmean)`` that is mean(x) - popmean, not mean(x).
    Needs SciPy >= 1.11, where these results expose ``df`` and ``confidence_interval()``.
    """
    if not (hasattr(result, "confidence_interval") and hasattr(result, "df") and hasattr(result, "statistic")):
        raise TypeError(
            "unsupported result: pass a scipy t-test result (SciPy >= 1.11), or give estimate= and se= directly"
        )
    try:
        df = float(np.asarray(result.df).item())
        stat = float(np.asarray(result.statistic).item())
        ci = result.confidence_interval(confidence_level=0.95)
        lo, hi = float(np.asarray(ci.low).item()), float(np.asarray(ci.high).item())
    except ValueError as exc:
        raise ValueError("pass the result of a single test (one estimate), not a batch of tests") from exc
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        raise ValueError("one-sided t-tests are not supported; run the test with alternative='two-sided'")
    source_eps = _source_epsilon(result.statistic, getattr(result, "_estimate", None),
                                 getattr(result, "_standard_error", None), ci.low, ci.high)
    err = _reconstruction_error(lo, hi, source_eps)
    se_ci = (hi - lo) / (2 * critical_value(0.95, df))
    mid = (lo + hi) / 2
    # SciPy keeps the standard error it computed from the data (a private attribute).
    # Prefer it: rebuilding it from the interval loses precision when the data sit far
    # from zero. Check it against the interval as far as the interval's precision allows.
    se_stored = _scalar(getattr(result, "_standard_error", None))
    if se_stored is not None and se_stored > 0:
        if not math.isclose(se_stored, se_ci, rel_tol=max(1e-6, 2 * err)):
            raise AdapterMismatch(
                f"the standard error SciPy stored ({se_stored:.6g}) does not match its confidence interval "
                f"(implied SE {se_ci:.6g}). Pass estimate=, se= and df= explicitly."
            )
        se = se_stored
    elif err > MAX_RECONSTRUCTION_ERROR:
        raise ValueError(
            f"the test's confidence interval is too narrow for its distance from zero to recover the standard "
            f"error (relative error up to {err:.1g}), and this SciPy version does not store it. Pass estimate=, "
            f"se= and df= explicitly, or subtract a nearby reference value from the data first."
        )
    else:
        se = se_ci
    stored_mean = _scalar(getattr(result, "_estimate", None))
    if stored_mean is not None and abs(stored_mean - mid) > 1e-6 * se + 8 * source_eps * max(abs(lo), abs(hi)):
        raise AdapterMismatch("SciPy's stored estimate is not the centre of its confidence interval. "
                              "Pass estimate=, se= and df= explicitly.")
    # SciPy does not retain popmean. Recover it approximately from its stored mean,
    # if available, and the tested difference. Even exact cancellation cannot prove
    # that the original null was zero: a sufficiently small null may have rounded away.
    est = stat * se
    centre = stored_mean if stored_mean is not None else mid
    candidate = centre - est
    # This is a conservative scale for rounding from subtraction and the statistic's
    # division/multiplication, not a confidence interval for the original null.
    noise = 4 * source_eps * max(abs(centre), abs(est), se)
    if se_stored is None or se_stored <= 0:
        noise += abs(est) * err
    if stored_mean is None:
        noise += 2 * source_eps * max(abs(lo), abs(hi))
    if not math.isfinite(candidate) or not math.isfinite(noise):
        raise ValueError("the test's null cannot be reconstructed at this scale; pass estimate= and se= directly")
    if abs(candidate) > noise:
        null = candidate
        if notes is not None:
            notes.append(f"The test's null was reconstructed as approximately {null:.12g}; SciPy does not store "
                         f"the original null, and rounding may affect it at a scale of about ±{noise:.2g}.")
    elif noise <= 1e-6 * se:
        # Keep the conventional 0.0 for well-conditioned zero-null tests, but make
        # the inferred (not known) status explicit in both notes and serialized input.
        null = 0.0
        if notes is not None:
            notes.append(f"The test's null is inferred as approximately 0; SciPy does not store the original "
                         f"null, so a nonzero null at the rounding scale (about ±{noise:.2g}) cannot be ruled out.")
    else:
        null = None
        if notes is not None:
            notes.append(f"The test's null cannot be reliably resolved at this data scale (rounding scale about "
                         f"±{noise:.2g}); it is recorded as unknown, not assumed to be zero.")
    note = _verify(est, se, df, stat, getattr(result, "pvalue", None), f"this {type(result).__name__}")
    if note and notes is not None:
        notes.append(note)
    return est, se, df, null


def from_statsmodels(result, term, notes: Optional[list] = None) -> Triple:
    """A fitted statsmodels results object and the name (or index) of one coefficient.

    Degrees of freedom follow statsmodels' own inference: ``df_resid_inference``
    when present (e.g. cluster-robust errors, where it is G - 1), otherwise
    ``df_resid``; a normal reference when the model was fitted with ``use_t=False``.
    """
    if term is None:
        raise ValueError("name the coefficient to interpret, e.g. analyze(fit, term='treatment')")
    try:
        est = float(result.params[term])
        se = float(result.bse[term])
    except (KeyError, IndexError, TypeError) as exc:
        raise KeyError(f"term {term!r} not found in the model's parameters") from exc
    df: Optional[float] = None
    if bool(getattr(result, "use_t", False)):
        d = getattr(result, "df_resid_inference", None)
        if d is None:
            d = getattr(result, "df_resid", None)
        df = None if d is None else float(d)
    def reported(name):
        values = getattr(result, name, None)
        try:
            return None if values is None else values[term]
        except (KeyError, IndexError, TypeError):
            return None

    note = _verify(est, se, df, reported("tvalues"), reported("pvalues"), f"term {term!r}")
    if note and notes is not None:
        notes.append(note)
    return est, se, df


def from_result(result, term=None) -> Tuple[float, float, Optional[float], str, Optional[float], list]:
    """(estimate, se, df, source label, null value, provenance notes)."""
    notes: list = []
    if hasattr(result, "params") and hasattr(result, "bse"):
        est, se, df = from_statsmodels(result, term, notes)
        return est, se, df, f"statsmodels:{type(result).__name__}[{term}]", 0.0, notes
    est, se, df, null = from_scipy(result, notes)
    label = f"scipy:{type(result).__name__}"
    if null is None:
        label += " (difference from an unknown test null)"
    elif null != 0.0:
        label += f" (difference from the test's null value {null:.6g}, reconstructed approximately)"
    return est, se, df, label, null, notes


def _is_missing(label) -> bool:
    """None, NaN, NaT, pandas NA and similar."""
    if label is None:
        return True
    try:
        return bool(label != label)
    except (TypeError, ValueError):  # pandas.NA refuses bool()
        return True


def paired_differences(a: Sequence[float], b: Sequence[float]) -> np.ndarray:
    """a - b per item, as floats. Integer scores are subtracted exactly before conversion,
    so large integers (beyond 2**53) do not lose their differences."""
    # dtype=object is essential: NumPy can infer float64 for a mixed-sign list
    # containing integers outside int64 and round the inputs before subtraction.
    ra, rb = np.asarray(a, dtype=object), np.asarray(b, dtype=object)
    if ra.shape != rb.shape or ra.ndim != 1:
        raise ValueError("a and b must be 1-D sequences of the same length (one score per item)")

    def exact(value):
        if isinstance(value, (int, np.integer, bool, np.bool_)):
            return Fraction(int(value))
        if isinstance(value, np.floating):
            if not np.isfinite(value):
                raise ValueError("scores must be finite")
            num, den = value.as_integer_ratio()
            return Fraction(int(num), int(den))
        try:
            return Fraction(value)
        except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
            raise ValueError("scores must be finite numbers") from exc

    differences = []
    for x, y in zip(ra.tolist(), rb.tolist()):
        diff = exact(x) - exact(y)
        try:
            converted = float(diff)
        except (OverflowError, ValueError) as exc:
            raise ValueError("score differences must be finite") from exc
        if not math.isfinite(converted):
            raise ValueError("score differences must be finite")
        if diff and converted == 0.0:
            raise ValueError("a score difference is too small to represent as a float")
        if diff.denominator == 1 and int(converted) != diff.numerator:
            raise ValueError("an integer score difference cannot be represented exactly as a float")
        differences.append(converted)
    return np.asarray(differences, dtype=float)


def paired(a: Sequence[float], b: Sequence[float], cluster: Optional[Sequence] = None) -> Triple:
    """Mean of item-level paired differences a - b, e.g. two models scored on the same questions.

    Without ``cluster`` the usual paired standard error is used (df = n - 1).
    With ``cluster`` (e.g. questions sharing a passage), a cluster-robust standard
    error with the G / (G - 1) small-sample factor is used (df = G - 1), following
    the clustered-error recommendation in Miller (2024), "Adding Error Bars to Evals".
    """
    d = paired_differences(a, b)
    n = d.size
    if n < 2:
        raise ValueError("need at least two paired items")
    with np.errstate(over="ignore", invalid="ignore"):
        mean = float(d.mean())
    if not math.isfinite(mean):
        raise ValueError("paired scores are too large for a finite mean; rescale the scores")
    if cluster is None:
        with np.errstate(over="ignore", invalid="ignore"):
            se = float(d.std(ddof=1) / math.sqrt(n))
        if not math.isfinite(se):
            raise ValueError("paired scores are too large for a finite standard error; rescale the scores")
        if se == 0:
            raise ValueError("all paired differences are identical; the standard error is zero")
        return mean, se, float(n - 1)

    labels = np.asarray(cluster, dtype=object)
    if labels.shape != d.shape:
        raise ValueError("cluster must give one label per item")
    missing = [i for i, label in enumerate(labels.tolist()) if _is_missing(label)]
    if missing:
        raise ValueError(
            f"{len(missing)} cluster label(s) are missing (first at item {missing[0]}). Missing labels would be merged "
            f"or split silently and change the standard error. Give every item a cluster, or drop those items."
        )
    groups = {}
    for label, value in zip(labels.tolist(), (d - mean).tolist()):
        groups[label] = groups.get(label, 0.0) + value
    G = len(groups)
    if G < 2:
        raise ValueError("need at least two clusters")
    sums = np.fromiter(groups.values(), dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        squared_sum = float(np.sum(sums**2))
    if not math.isfinite(squared_sum):
        raise ValueError("paired scores are too large for a finite standard error; rescale the scores")
    se = float(math.sqrt(squared_sum * G / (G - 1)) / n)
    if not math.isfinite(se):
        raise ValueError("paired scores are too large for a finite standard error; rescale the scores")
    if se == 0:
        raise ValueError("the cluster-robust standard error is zero")
    return mean, se, float(G - 1)
