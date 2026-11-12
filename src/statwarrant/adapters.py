"""Turn common Python outputs into (estimate, standard error, degrees of freedom).

Every adapter checks its own work: after extracting the numbers it recomputes the
two-sided p-value with statwarrant's reference distribution and compares it with
the p-value the original object reports. If they disagree, the adapter raises
instead of interpreting a different test from the one that was run.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

import numpy as np

from ._core import _dist, critical_value

Triple = Tuple[float, float, Optional[float]]


class AdapterMismatch(ValueError):
    """statwarrant could not reproduce the p-value reported by the original result."""


def _p_two_sided(est: float, se: float, df: Optional[float]) -> float:
    return float(min(1.0, 2 * _dist(df).sf(abs(est) / se)))


def _scalar(x) -> Optional[float]:
    try:
        v = float(np.asarray(x).item())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _verify(est: float, se: float, df: Optional[float], reported_stat, reported_p, what: str) -> None:
    """Stop unless statwarrant reproduces the original test statistic and p-value.

    Both comparisons are relative, so they behave the same whatever the scale of the
    data. A p-value too small to compare in floating point (below 1e-250) is checked
    through the statistic alone.
    """
    advice = "Rather than interpret a different test, statwarrant stops here. Pass estimate=, se= and df= explicitly."
    stat, p = _scalar(reported_stat), _scalar(reported_p)
    if stat is None or p is None:
        raise AdapterMismatch(f"{what} does not report a finite test statistic and p-value, so statwarrant cannot "
                              f"check that it reads the same test. {advice}")
    mine_stat = est / se
    if not math.isclose(mine_stat, stat, rel_tol=1e-6, abs_tol=1e-9):
        raise AdapterMismatch(f"statwarrant reads {what} as estimate {est:.6g} and SE {se:.6g} (statistic "
                              f"{mine_stat:.6g}), but the result reports statistic {stat:.6g}. {advice}")
    mine_p = _p_two_sided(est, se, df)
    # Skip the p-value comparison only when both values underflow; one tiny and one
    # ordinary p-value is a real disagreement.
    if max(mine_p, p) > 1e-250 and not math.isclose(mine_p, p, rel_tol=1e-6, abs_tol=0.0):
        raise AdapterMismatch(
            f"statwarrant reads {what} with {'a normal reference' if df is None else f'df {df:.6g}'}, giving "
            f"p = {mine_p:.6g}, but the result reports p = {p:.6g}. {advice}"
        )


_EPS = float(np.finfo(float).eps)
# Largest relative error in a standard error recovered from interval endpoints that
# statwarrant accepts.
MAX_RECONSTRUCTION_ERROR = 1e-6


def _reconstruction_error(lo: float, hi: float) -> float:
    """Bound on the relative error of (hi - lo) when each endpoint carries rounding error.

    Endpoints far from zero relative to the interval's width (e.g. 1e14 +/- 0.3) lose
    most of their significant digits on subtraction.
    """
    return 4 * _EPS * max(abs(lo), abs(hi)) / (hi - lo)


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


def from_scipy(result) -> Tuple[float, float, Optional[float], float]:
    """scipy.stats t-test results (ttest_ind, ttest_rel, ttest_1samp).

    Returns (estimate, se, df, null). The estimate is the difference the test
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
    err = _reconstruction_error(lo, hi)
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
    if stored_mean is not None and abs(stored_mean - mid) > 1e-6 * se + 8 * _EPS * max(abs(lo), abs(hi)):
        raise AdapterMismatch("SciPy's stored estimate is not the centre of its confidence interval. "
                              "Pass estimate=, se= and df= explicitly.")
    # The statistic is (mean - null) / se, so the tested difference is statistic x se,
    # whatever the scale of the data, and the null is what remains.
    est = stat * se
    null = mid - est
    if abs(null) <= 1e-9 * max(abs(mid), se):  # relative only: floating-point noise around a zero null
        null = 0.0
    _verify(est, se, df, stat, getattr(result, "pvalue", None), f"this {type(result).__name__}")
    return est, se, df, null


def from_statsmodels(result, term) -> Triple:
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

    _verify(est, se, df, reported("tvalues"), reported("pvalues"), f"term {term!r}")
    return est, se, df


def from_result(result, term=None) -> Tuple[float, float, Optional[float], str, float]:
    if hasattr(result, "params") and hasattr(result, "bse"):
        est, se, df = from_statsmodels(result, term)
        return est, se, df, f"statsmodels:{type(result).__name__}[{term}]", 0.0
    est, se, df, null = from_scipy(result)
    label = f"scipy:{type(result).__name__}"
    if null != 0.0:
        label += f" (difference from the test's null value {null:.6g})"
    return est, se, df, label, null


def _is_missing(label) -> bool:
    """None, NaN, NaT, pandas NA and similar."""
    if label is None:
        return True
    try:
        return bool(label != label)
    except (TypeError, ValueError):  # pandas.NA refuses bool()
        return True


def paired(a: Sequence[float], b: Sequence[float], cluster: Optional[Sequence] = None) -> Triple:
    """Mean of item-level paired differences a - b, e.g. two models scored on the same questions.

    Without ``cluster`` the usual paired standard error is used (df = n - 1).
    With ``cluster`` (e.g. questions sharing a passage), a cluster-robust standard
    error with the G / (G - 1) small-sample factor is used (df = G - 1), following
    the clustered-error recommendation in Miller (2024), "Adding Error Bars to Evals".
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("a and b must be 1-D sequences of the same length (one score per item)")
    if not (np.all(np.isfinite(a)) and np.all(np.isfinite(b))):
        raise ValueError("scores must be finite")
    d = a - b
    n = d.size
    if n < 2:
        raise ValueError("need at least two paired items")
    mean = float(d.mean())
    if cluster is None:
        se = float(d.std(ddof=1) / math.sqrt(n))
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
    se = float(math.sqrt(np.sum(sums**2) * G / (G - 1)) / n)
    if se == 0:
        raise ValueError("the cluster-robust standard error is zero")
    return mean, se, float(G - 1)
