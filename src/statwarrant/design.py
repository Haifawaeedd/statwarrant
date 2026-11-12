"""Design sensitivity: power, Type S and Type M (exaggeration) under assumed effects.

These numbers describe how *the design* behaves if the true effect were the
assumed value. They are not a verdict on the observed estimate, and they must
not be used to "correct" it (Gelman & Carlin, 2014; Lu, Qiu & Deng, 2018).

The calculations use the normal approximation with the study's standard error.
For an estimate X ~ N(A, s^2) and two-sided critical value c = z * s:

* power = P(|X| > c)
* Type S = P(sign of X opposite to A | |X| > c), undefined for A = 0
* exaggeration ratio = E[|X| | |X| > c] / |A|, undefined for A = 0,
  computed exactly from truncated-normal moments.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from scipy import stats

from ._core import level_text
from .claims import fmt


def _pdf(x: float) -> float:
    # The normal density underflows to 0 beyond |x| of about 38.5; skip it there (and
    # avoid an overflow warning when squaring a huge x).
    return 0.0 if abs(x) > 40 else float(stats.norm.pdf(x))


def _ratio(x: float) -> str:
    return f"{x:.2f}" if x < 1e6 else f"{x:.3g}"


def _pct(x: float) -> str:
    return "less than 0.1%" if x < 0.001 else f"{x:.1%}"


@dataclass(frozen=True)
class DesignPoint:
    assumed_effect: float
    power: float
    type_s: Optional[float]
    exaggeration: Optional[float]

    def sentence(self, se: float, alpha: float) -> str:
        if self.assumed_effect == 0:
            return (
                f"Under an assumed true effect of 0, the chance of a significant result equals alpha "
                f"({level_text(alpha)}). Type S and the exaggeration ratio are undefined: a zero effect has no sign, "
                f"and the ratio would divide by zero."
            )
        return (
            f"Under an assumed true effect of {fmt(self.assumed_effect)} and this design (SE = {fmt(se)}), "
            f"the chance of a significant result is {self.power:.0%}. Among significant results, "
            f"{_pct(self.type_s)} would have the wrong sign, and their magnitude would on average be "
            f"{_ratio(self.exaggeration)} times the true effect."
        )

    def to_dict(self) -> dict:
        return {
            "assumed_effect": self.assumed_effect,
            "power": self.power,
            "type_s": self.type_s,
            "exaggeration_ratio": self.exaggeration,
        }


def design_point(assumed_effect: float, se: float, alpha: float = 0.05) -> DesignPoint:
    """Power, Type S and exaggeration ratio for one assumed true effect."""
    if se <= 0 or not math.isfinite(se):
        raise ValueError("se must be a positive finite number")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    A = float(assumed_effect)
    if not math.isfinite(A):
        raise ValueError("assumed effects must be finite numbers")
    z = stats.norm.ppf(1 - alpha / 2)
    # Work in units of the standard error (r = A / se), so that neither a huge SE nor a
    # huge effect overflows the intermediate quantities.
    r = A / se
    if not math.isfinite(r):  # |A| beyond any multiple of se: the limits hold exactly
        return DesignPoint(A, 1.0, 0.0, 1.0)
    a = z - r  # standardised upper cut
    b = -z - r  # standardised lower cut
    p_hi = float(stats.norm.sf(a))
    p_lo = float(stats.norm.cdf(b))
    power = p_hi + p_lo
    if A == 0:
        return DesignPoint(0.0, power, None, None)

    type_s = (p_lo if A > 0 else p_hi) / power
    # E[|X| ; |X| > c] / se for X ~ N(A, se^2)
    upper = r * p_hi + _pdf(a)
    lower = r * p_lo - _pdf(b)
    denominator = power * abs(r)
    exaggeration = (upper - lower) / denominator if denominator > 0 else math.inf
    if not math.isfinite(exaggeration):
        raise ValueError(
            f"the assumed effect {A:g} is too small relative to the standard error ({se:g}) for its "
            f"exaggeration ratio to be represented; give assumed effects on the scale of plausible true effects"
        )
    return DesignPoint(A, power, type_s, exaggeration)


@dataclass
class DesignTable:
    se: float
    alpha: float
    source: str
    points: List[DesignPoint]
    warnings: List[str] = field(default_factory=list)

    def sentences(self) -> List[str]:
        return [p.sentence(self.se, self.alpha) for p in self.points]

    def to_dict(self) -> dict:
        return {
            "se": self.se,
            "alpha": self.alpha,
            "assumption_source": self.source,
            "method": "normal approximation, exact truncated-normal moments",
            "points": [p.to_dict() for p in self.points],
            "warnings": list(self.warnings),
        }

    def to_markdown(self) -> str:
        rows = ["| Assumed effect | Power | Type S | Exaggeration ratio |", "| --- | --- | --- | --- |"]
        for p in self.points:
            ts = "undefined" if p.type_s is None else f"{p.type_s:.3f}"
            ex = "undefined" if p.exaggeration is None else _ratio(p.exaggeration)
            rows.append(f"| {fmt(p.assumed_effect)} | {p.power:.3f} | {ts} | {ex} |")
        out = [
            "### Design sensitivity",
            "",
            f"Assumed effects from: {self.source}. These describe the design, not the observed result.",
            "",
            *rows,
        ]
        if self.warnings:
            out += ["", *[f"- {w}" for w in self.warnings]]
        return "\n".join(out)

    def __str__(self) -> str:
        return "\n".join(self.sentences() + self.warnings)


def design_table(
    assumed_effects: Sequence[float],
    se: float,
    alpha: float,
    source: str,
    observed: Optional[float] = None,
    df: Optional[float] = None,
) -> DesignTable:
    effects = [float(x) for x in assumed_effects]
    if not all(math.isfinite(x) for x in effects):
        raise ValueError("assumed effects must be finite numbers")
    if observed is not None and not math.isfinite(float(observed)):
        raise ValueError("the observed estimate must be a finite number")
    if len(effects) < 2:
        raise ValueError(
            "give a range of at least two plausible effects; a single value hides how sensitive the design is"
        )
    if not source or not str(source).strip():
        raise ValueError("state where the assumed effects come from (source=...), e.g. a prior study or meta-analysis")
    table = DesignTable(se, alpha, str(source), [design_point(a, se, alpha) for a in effects])
    if observed is not None and any(math.isclose(a, observed, rel_tol=1e-9, abs_tol=1e-12) for a in effects):
        table.warnings.append(
            "One assumed effect equals the observed estimate. That is allowed, but on its own it reproduces "
            "'observed power', which says nothing new; prefer values from outside this study."
        )
    if df is not None and math.isfinite(df) and df < 30:
        table.warnings.append(
            f"Normal approximation with df = {fmt(df)}: exact t-based values differ when df is small."
        )
    return table
