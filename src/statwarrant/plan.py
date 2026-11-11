"""Declare first, analyse second.

The smallest effect size of interest (SESOI) and its justification are fixed in
:func:`declare` before any result is seen. :meth:`Plan.analyze` then reads a
result and returns what it supports.
"""

from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple, Union

from . import adapters
from ._core import POLICIES, Evidence, critical_value, evaluate
from .claims import CheckResult, Claims, Context, build_claims, check_sentence, fmt
from .design import DesignTable, design_table

Number = Union[int, float]


@dataclass(frozen=True)
class Plan:
    sesoi: Optional[Tuple[float, float]]
    sesoi_source: Optional[str]
    alpha: float
    interval_policy: str
    units: Optional[str]
    scope: Optional[str]
    better: str
    declared_at: str

    # ------------------------------------------------------------------ #
    def analyze(
        self,
        result=None,
        *,
        term=None,
        estimate: Optional[Number] = None,
        se: Optional[Number] = None,
        df: Optional[Number] = None,
        ci: Optional[Tuple[Number, Number]] = None,
        ci_level: float = 0.95,
        baseline: Optional[Number] = None,
    ) -> "Result":
        """Interpret one effect.

        Give exactly one of: a fitted result (scipy t-test, or statsmodels with
        ``term=``); ``estimate`` and ``se``; or ``ci`` (optionally with ``estimate``).
        ``baseline`` is the reference level of the outcome, used to report the
        absolute and the relative change side by side.
        """
        given = sum(x is not None for x in (result, se, ci))
        if given != 1:
            raise ValueError("give exactly one of: a fitted result, se=..., or ci=(lower, upper)")

        if result is not None:
            est, s, d, source = adapters.from_result(result, term)
        elif ci is not None:
            mid, s = adapters.from_ci(float(ci[0]), float(ci[1]), ci_level, df)
            est = mid if estimate is None else float(estimate)
            if estimate is not None and not math.isclose(est, mid, rel_tol=1e-6, abs_tol=1e-9 * max(1.0, abs(mid))):
                warnings.warn(
                    "the interval is not symmetric around the estimate; for ratios (odds, risk, hazard) "
                    "give the estimate and interval on the log scale",
                    UserWarning,
                    stacklevel=2,
                )
            d = None if df is None else float(df)
            source = f"interval ({ci_level:.0%})"
        else:
            if estimate is None:
                raise ValueError("estimate= is required together with se=")
            est, s = float(estimate), float(se)
            d = None if df is None else float(df)
            source = "estimate and standard error"

        return self._finish(est, s, d, source, baseline)

    def analyze_paired(
        self,
        a: Sequence[float],
        b: Sequence[float],
        *,
        cluster: Optional[Sequence] = None,
        baseline: Optional[Number] = None,
    ) -> "Result":
        """Item-level paired scores, e.g. model A and model B on the same test questions (A - B)."""
        est, s, d = adapters.paired(a, b, cluster)
        source = "paired item scores" + (" (cluster-robust SE)" if cluster is not None else "")
        return self._finish(est, s, d, source, baseline)

    def _finish(self, est, s, d, source, baseline) -> "Result":
        ev = evaluate(est, s, d, self.alpha, self.interval_policy, self.sesoi)
        ctx = Context(ev, self.units, self.scope, self.better, None if baseline is None else float(baseline))
        return Result(plan=self, evidence=ev, context=ctx, claims=build_claims(ctx), source=source)

    def to_dict(self) -> dict:
        return {
            "sesoi": list(self.sesoi) if self.sesoi else None,
            "sesoi_source": self.sesoi_source,
            "alpha": self.alpha,
            "interval_policy": self.interval_policy,
            "units": self.units,
            "scope": self.scope,
            "better": self.better,
            "declared_at": self.declared_at,
        }


def declare(
    *,
    sesoi: Optional[Union[Number, Tuple[Number, Number]]] = None,
    sesoi_source: Optional[str] = None,
    alpha: float = 0.05,
    interval_policy: str = "single",
    units: Optional[str] = None,
    scope: Optional[str] = None,
    better: str = "higher",
) -> Plan:
    """Fix the rules of interpretation before looking at the result.

    Parameters
    ----------
    sesoi : float or (low, high), optional
        Smallest effect size of interest. A single number d means (-d, d).
        Without it, claims about practical importance and equivalence are withheld.
    sesoi_source : str
        Required with ``sesoi``: why this threshold (an anchor, a cost, a prior
        consensus). A threshold without a reason is not accepted.
    alpha : float
        Significance level. Default 0.05.
    interval_policy : {"single", "standard"}
        "single" reads every decision from one (1 - alpha) interval (default).
        "standard" uses (1 - 2 alpha) for equivalence and minimal-effect tests, as TOSTER does.
    units : str, optional
        Units of the effect, used in sentences ("points", "proportion", ...).
    scope : str, optional
        Population, data and conditions the result comes from. Attached to claims.
    better : {"higher", "lower"}
        Whether larger values of the outcome are better; used to read words like "improves".
    """
    if interval_policy not in POLICIES:
        raise ValueError(f"interval_policy must be one of {POLICIES}")
    if better not in ("higher", "lower"):
        raise ValueError("better must be 'higher' or 'lower'")
    if not 0 < alpha < 0.5:
        raise ValueError("alpha must be between 0 and 0.5")

    bounds = None
    if sesoi is not None:
        if not sesoi_source or not str(sesoi_source).strip():
            raise ValueError(
                "a smallest effect size of interest needs a stated reason: pass sesoi_source='...' "
                "(e.g. 'smallest change teachers consider worth acting on')"
            )
        if isinstance(sesoi, (int, float)):
            if not sesoi > 0:
                raise ValueError("a single sesoi value must be positive; it means (-sesoi, +sesoi)")
            bounds = (-float(sesoi), float(sesoi))
        else:
            low, high = (float(x) for x in sesoi)
            if not low < 0 < high:
                raise ValueError("sesoi bounds must satisfy low < 0 < high")
            bounds = (low, high)

    return Plan(
        sesoi=bounds,
        sesoi_source=None if sesoi_source is None else str(sesoi_source),
        alpha=float(alpha),
        interval_policy=interval_policy,
        units=units,
        scope=scope,
        better=better,
        declared_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


@dataclass
class Result:
    plan: Plan
    evidence: Evidence
    context: Context
    claims: Claims
    source: str
    _design: Optional[DesignTable] = field(default=None, repr=False)

    # ------------------------------------------------------------------ #
    def check(self, sentence: str) -> CheckResult:
        """Judge a sentence you intend to write against this result."""
        return check_sentence(sentence, self.context)

    def design(self, assumed_effects: Sequence[float], *, source: str) -> DesignTable:
        """Power, Type S and exaggeration ratio of this design under assumed true effects."""
        ev = self.evidence
        self._design = design_table(assumed_effects, ev.se, self.plan.alpha, source, ev.estimate, ev.df)
        return self._design

    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        out = {
            "statwarrant_version": _version(),
            "plan": self.plan.to_dict(),
            "input": self.source,
            "evidence": self.evidence.to_dict(),
            "claims": self.claims.to_dict(),
        }
        if self.context.baseline is not None:
            out["reporting"] = {
                "baseline": self.context.baseline,
                "absolute_change": self.evidence.estimate,
                "relative_change": self.evidence.estimate / self.context.baseline,
            }
        if self._design is not None:
            out["design"] = self._design.to_dict()
        return out

    def to_json(self, **kwargs) -> str:
        kwargs.setdefault("indent", 2)
        return json.dumps(self.to_dict(), **kwargs)

    def to_markdown(self) -> str:
        ev = self.evidence
        p = self.plan
        lines = ["## statwarrant result", ""]
        lines.append(f"**Estimate:** {fmt(ev.estimate)}{' ' + p.units if p.units else ''} (SE {fmt(ev.se)}"
                     f"{'' if ev.df is None else f', df {fmt(ev.df)}'}) from {self.source}.")
        if p.scope:
            lines.append(f"**Scope:** {p.scope}")
        if p.sesoi:
            lines.append(f"**Smallest effect size of interest:** [{fmt(p.sesoi[0])}, {fmt(p.sesoi[1])}], "
                         f"because: {p.sesoi_source}")
        lines.append(f"**Interval policy:** {p.interval_policy}, alpha = {p.alpha}")
        lines += ["", "| Test | Interval | p-value | Decision |", "| --- | --- | --- | --- |"]
        lo, hi = ev.zero_interval
        lines.append(f"| Differs from zero | {ev.zero_level:.0%} [{fmt(lo)}, {fmt(hi)}] | {fmt(ev.p_zero)} | "
                     f"{'yes' if ev.differs_from_zero else 'not established'} |")
        if p.sesoi:
            blo, bhi = ev.bounds_interval
            iv = f"{ev.bounds_level:.0%} [{fmt(blo)}, {fmt(bhi)}]"
            lines.append(f"| Equivalent (TOST) | {iv} | {fmt(ev.p_equivalence)} | "
                         f"{'yes' if ev.equivalent else 'not established'} |")
            lines.append(f"| Exceeds SESOI (MET) | {iv} | {fmt(ev.p_minimal_effect)} | "
                         f"{'yes' if ev.exceeds_sesoi else 'not established'} |")
        lines += ["", "### You can say"]
        lines += [f"- {c.text}" for c in self.claims.allowed]
        lines += ["", "### Do not say"]
        lines += [f"- ~~{c.text}~~ {c.reason}" for c in self.claims.blocked]
        if self.claims.notes:
            lines += ["", "### Notes"] + [f"- {n}" for n in self.claims.notes]
        if self._design is not None:
            lines += ["", self._design.to_markdown()]
        return "\n".join(lines)

    def __str__(self) -> str:
        parts = [c.text for c in self.claims.allowed]
        if self.claims.blocked:
            parts.append("Do not say: " + "; ".join(f"\"{c.text}\"" for c in self.claims.blocked))
        parts += self.claims.notes
        return "\n".join(parts)


def _version() -> str:
    from . import __version__

    return __version__
