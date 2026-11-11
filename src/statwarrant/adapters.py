"""Turn common Python outputs into (estimate, standard error, degrees of freedom)."""

from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

import numpy as np

from ._core import critical_value

Triple = Tuple[float, float, Optional[float]]


def from_ci(lo: float, hi: float, level: float = 0.95, df: Optional[float] = None) -> Tuple[float, float]:
    """Midpoint and standard error implied by a symmetric two-sided interval."""
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        raise ValueError("the interval must be finite with lower < upper (two-sided intervals only)")
    se = (hi - lo) / (2 * critical_value(level, df))
    return (lo + hi) / 2, se


def from_scipy(result) -> Triple:
    """scipy.stats t-test results (ttest_ind, ttest_rel, ttest_1samp).

    Needs SciPy >= 1.11, where these results expose ``df`` and ``confidence_interval()``.
    """
    if not (hasattr(result, "confidence_interval") and hasattr(result, "df")):
        raise TypeError(
            "unsupported result: pass a scipy t-test result (SciPy >= 1.11), or give estimate= and se= directly"
        )
    df = float(np.asarray(result.df).item())
    ci = result.confidence_interval(confidence_level=0.95)
    lo, hi = float(np.asarray(ci.low).item()), float(np.asarray(ci.high).item())
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise ValueError("one-sided t-tests are not supported; run the test with alternative='two-sided'")
    est, se = from_ci(lo, hi, 0.95, df)
    return est, se, df


def from_statsmodels(result, term) -> Triple:
    """A fitted statsmodels results object and the name (or index) of one coefficient."""
    if term is None:
        raise ValueError("name the coefficient to interpret, e.g. analyze(fit, term='treatment')")
    try:
        est = float(result.params[term])
        se = float(result.bse[term])
    except (KeyError, IndexError, TypeError) as exc:
        raise KeyError(f"term {term!r} not found in the model's parameters") from exc
    use_t = bool(getattr(result, "use_t", False))
    df = float(result.df_resid) if use_t and hasattr(result, "df_resid") else None
    return est, se, df


def from_result(result, term=None) -> Tuple[float, float, Optional[float], str]:
    if hasattr(result, "params") and hasattr(result, "bse"):
        est, se, df = from_statsmodels(result, term)
        return est, se, df, f"statsmodels:{type(result).__name__}[{term}]"
    est, se, df = from_scipy(result)
    return est, se, df, f"scipy:{type(result).__name__}"


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
        return mean, se, float(n - 1)

    labels = np.asarray(cluster)
    if labels.shape != d.shape:
        raise ValueError("cluster must give one label per item")
    groups = {}
    for label, value in zip(labels.tolist(), (d - mean).tolist()):
        groups[label] = groups.get(label, 0.0) + value
    G = len(groups)
    if G < 2:
        raise ValueError("need at least two clusters")
    sums = np.fromiter(groups.values(), dtype=float)
    se = float(math.sqrt(np.sum(sums**2) * G / (G - 1)) / n)
    return mean, se, float(G - 1)
