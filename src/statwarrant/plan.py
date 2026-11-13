"""Declare first, analyse second.

The smallest effect size of interest (SESOI) and its justification are fixed in
:func:`declare` before any result is seen. :meth:`Plan.analyze` then reads a
result and returns what it supports.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from numbers import Number as Numeric

import numpy as np
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple, Union

from . import adapters
from ._core import MIN_ALPHA, POLICIES, Evidence, Thresholds, evaluate, level_text
from ._precision import checked_float
from ._version import __version__
from .claims import CheckResult, Claims, Context, build_claims, check_sentence, fmt, fmt_bound, fmt_bounds, fmt_ci, fmt_p
from .design import DesignTable, design_table

# An estimate given with an interval may differ from the interval's midpoint by
# rounding; beyond this share of the half-width the interval is treated as
# asymmetric and refused.
SYMMETRY_TOLERANCE = 0.05

SCHEMA = "statwarrant-result/2"

# Below this many items that differ between the two conditions, analyze_paired adds a
# caution: the t approximation behind the interval can be poor.
FEW_DIFFERING_ITEMS = 10


def _round_dir(x: float, up: bool, sig: int = 4) -> str:
    """``x`` to ``sig`` significant digits, rounded down or up exactly (decimal arithmetic)."""
    if x == 0 or not math.isfinite(x):
        return fmt(x)
    d = Decimal(repr(x))
    q = Decimal(1).scaleb(d.adjusted() - sig + 1)
    r = d.quantize(q, rounding=ROUND_CEILING if up else ROUND_FLOOR)
    return format(r.normalize(), "g") if abs(r.adjusted()) >= 5 else format(r, "f")


def fmt_down(x: float) -> str:
    """For "every d below x": never shown larger than x, so the statement stays true."""
    return _round_dir(x, up=False)


def fmt_up(x: float) -> str:
    """For "every d above x": never shown smaller than x, so the statement stays true."""
    return _round_dir(x, up=True)


def _raw(x):
    """A submitted number as given, JSON-safe: non-finite values are kept as text ("inf")."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError, OverflowError):
        return str(x)
    return v if math.isfinite(v) else str(v)


def _term_value(result, name: str, term):
    values = getattr(result, name, None)
    try:
        return _scalar(values[term]) if values is not None else None
    except (KeyError, IndexError, TypeError):
        return None


def _scalar(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None

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
    outcome: Optional[str] = None
    contrast: Optional[str] = None
    registration: Optional[str] = None
    design: Optional[str] = None
    subgroup: Optional[str] = None

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
        label: Optional[str] = None,
        ratio: bool = False,
    ) -> "Result":
        """Interpret one effect.

        Give exactly one of: a fitted result (scipy t-test, or statsmodels with
        ``term=``); ``estimate`` and ``se``; or ``ci`` (optionally with ``estimate``).

        With ``ci``, the interval must be symmetric (a Wald-type interval). An
        ``estimate`` given alongside it is checked against the midpoint and must
        agree up to rounding; the midpoint is then used, so the published interval
        is reproduced exactly. Asymmetric intervals (odds, risk or hazard ratios,
        bootstrap intervals) are refused: give log-scale numbers, or ``estimate``
        and ``se``.

        With ``ratio=True``, ``estimate`` and ``ci`` are a published odds, risk, rate or
        hazard ratio and its interval, as printed; statwarrant analyses them on the log
        scale. The symmetry check then allows for the rounding of the printed digits
        (inferred from the numbers as given), as it does on the linear scale.

        ``baseline`` is the reference level of the outcome, used to report the
        absolute and the relative change side by side. ``label`` names this
        result (e.g. "H1, main effect") so sentences and reports point to it.

        Explicit integral inputs that cannot be represented exactly as floats
        are refused. Numbers already rounded to floats cannot be recovered.
        """
        given = sum(x is not None for x in (result, se, ci))
        if given != 1:
            raise ValueError("give exactly one of: a fitted result, se=..., or ci=(lower, upper)")

        if baseline is not None:
            checked_float(baseline, "baseline")
        est_input = checked_float(estimate, "estimate") if result is None and estimate is not None else None
        se_input = checked_float(se, "se") if se is not None else None
        df_input = checked_float(df, "df") if result is None and df is not None else None
        if ci is not None:
            lo = checked_float(ci[0], "ci lower bound")
            hi = checked_float(ci[1], "ci upper bound")
        rounding = 0.0
        if baseline is not None and (ratio or _log_scale(self.units)):
            raise ValueError(
                "a baseline cannot be combined with a ratio or a log-scale result: the result is already relative "
                "(a ratio of 0.83 is a change of -17%), and dividing its log by a baseline would give a meaningless "
                "relative change. Omit baseline=; with ratio=True statwarrant reports the change on the ratio scale.")
        if ratio:
            if ci is None or result is not None:
                raise ValueError("ratio=True needs ci=(lower, upper) on the ratio scale (optionally with estimate=)")
            values = [lo, hi] + ([est_input] if est_input is not None else [])
            if not all(math.isfinite(v) and v > 0 for v in values):
                raise ValueError("ratios and their interval must be finite and positive")
            # rounding of the printed digits (all three printed to the same precision), on the log scale
            unit = _half_unit(*values)
            rounding = sum(unit / v for v in values[2:]) + (unit / lo + unit / hi) / 2
            lo, hi = math.log(lo), math.log(hi)
            est_input = None if est_input is None else math.log(est_input)
        elif ci is not None and est_input is not None:
            rounding = 2 * _half_unit(est_input, lo, hi)

        null = 0.0
        provenance: list = []
        raw = {"estimate": _raw(estimate), "se": _raw(se), "df": _raw(df),
               "ci": None if ci is None else [_raw(ci[0]), _raw(ci[1])],
               "ci_level": ci_level if ci is not None else None, "baseline": _raw(baseline),
               **({"ratio_scale_input": True} if ratio else {})}
        if result is not None:
            est, s, d, source, null, provenance = adapters.from_result(result, term)
            if hasattr(result, "params"):  # statsmodels: the statistic and p-value of this term
                rep_stat, rep_p = _term_value(result, "tvalues", term), _term_value(result, "pvalues", term)
            else:
                rep_stat, rep_p = _scalar(getattr(result, "statistic", None)), _scalar(getattr(result, "pvalue", None))
            raw = {"result_type": type(result).__name__, "term": None if term is None else str(term),
                   "reported_statistic": rep_stat, "reported_p": rep_p, "baseline": raw["baseline"]}
        elif ci is not None:
            mid, s = adapters.from_ci(lo, hi, ci_level, df_input)
            if estimate is not None:
                gap = abs(est_input - mid)
                half = (hi - lo) / 2
                if not math.isfinite(est_input) or gap > SYMMETRY_TOLERANCE * half + rounding:
                    raise ValueError(
                        f"the interval ({fmt(lo)}, {fmt(hi)}) is not symmetric around the estimate {fmt(est_input)} "
                        f"(midpoint {fmt(mid)}). statwarrant reads intervals as estimate +/- critical value x SE, so an "
                        f"asymmetric interval would be misread. For ratios (odds, risk, hazard) give the log estimate "
                        f"and log interval; otherwise pass estimate= and se= directly."
                    )
                if gap > 1e-12 * max(1.0, abs(mid)):
                    shown = (lambda x: f"{math.exp(x):.6g}") if ratio else (lambda x: f"{x:.6g}")
                    if gap <= rounding:
                        provenance.append(f"The estimate given ({shown(est_input)}) differs from the interval's "
                                          f"midpoint ({shown(mid)}) by no more than rounding of the printed numbers "
                                          f"explains. statwarrant uses the midpoint, so the interval is reproduced.")
                    else:
                        scale = " on the log scale" if ratio else ""
                        provenance.append(
                            f"The estimate given ({shown(est_input)}) is {gap:.3g}{scale} from the interval's midpoint "
                            f"({shown(mid)}): more than rounding of the printed numbers explains (up to "
                            f"{rounding:.3g}), but within the asymmetry statwarrant tolerates "
                            f"({SYMMETRY_TOLERANCE * half + rounding:.3g}: {SYMMETRY_TOLERANCE:.0%} of the half-width "
                            f"plus rounding). statwarrant uses the midpoint, so the interval is reproduced and the "
                            f"estimate given is not; check that the estimate and the interval belong together.")
                    raw["estimate_vs_midpoint"] = {"given": _raw(est_input), "midpoint": _raw(mid),
                                                   "explained_by_rounding": gap <= rounding}
            est = mid
            d = df_input
            source = f"interval ({level_text(ci_level)})" + (", ratio scale, analysed as logs" if ratio else "")
        else:
            if estimate is None:
                raise ValueError("estimate= is required together with se=")
            est, s = est_input, se_input
            d = df_input
            source = "estimate and standard error"

        res = self._finish(est, s, d, source, baseline, null, label, raw)
        if ratio and self.units and not _log_scale(self.units):
            provenance.append(f"ratio=True analyses the log of the ratio, so the estimate, interval and thresholds reported are log ratios; the "
                              f"declared units ({self.units!r}) do not say so. Declare units such as 'log "
                              f"{self.units}' to make reports read correctly.")
        if ratio:
            lo_r, hi_r = (math.exp(x) for x in res.evidence.zero_interval)
            mid_r = math.exp(res.evidence.estimate)
            provenance.append(f"On the ratio scale: {mid_r:.4g} ({level_text(res.evidence.zero_level)} CI {lo_r:.4g} "
                              f"to {hi_r:.4g}), a relative change of {mid_r - 1:+.1%} ({lo_r - 1:+.1%} to "
                              f"{hi_r - 1:+.1%}).")
        for note in reversed(provenance):
            res.claims.notes.insert(0, note)
        if provenance:
            res.raw_input["provenance_notes"] = list(provenance)
        return res

    def analyze_paired(
        self,
        a: Sequence[float],
        b: Sequence[float],
        *,
        cluster: Optional[Sequence] = None,
        baseline: Optional[Number] = None,
        label: Optional[str] = None,
    ) -> "Result":
        """Item-level paired scores, e.g. model A and model B on the same test questions (A - B)."""
        if baseline is not None:
            checked_float(baseline, "baseline")
        est, s, d = adapters.paired(a, b, cluster)
        source = "paired item scores" + (" (cluster-robust SE)" if cluster is not None else "")
        differing = int(np.count_nonzero(adapters.paired_differences(a, b)))
        # n_clusters comes from the same grouping the inference used (df = G - 1).
        raw = {"n_items": len(a), "n_differing_items": differing,
               "n_clusters": None if cluster is None else int(round(d)) + 1, "baseline": _raw(baseline)}
        res = self._finish(est, s, d, source, baseline, 0.0, label, raw)
        if differing < FEW_DIFFERING_ITEMS:
            res.claims.notes.insert(0, (
                f"Only {differing} of {len(a)} items differ between the two conditions. The interval is a t "
                f"approximation, which can be poor with so few differing items; the conclusion is conditional on "
                f"it. Check it with an exact method for paired data (e.g. an exact interval on the discordant items)."))
        return res

    def _finish(self, est, s, d, source, baseline, null: Optional[float] = 0.0, label: Optional[str] = None,
                raw: Optional[dict] = None) -> "Result":
        if baseline is not None:
            baseline = checked_float(baseline, "baseline")
            if not math.isfinite(baseline) or baseline == 0:
                raise ValueError("baseline must be a finite, non-zero number (a relative change needs a non-zero reference)")
        ev = evaluate(est, s, d, self.alpha, self.interval_policy, self.sesoi)
        if baseline is not None:
            relative = [x / baseline for x in (ev.estimate, *ev.zero_interval)]
            if not all(math.isfinite(x) for x in relative):
                raise ValueError("the baseline is too small for the estimate: the relative change overflows. "
                                 "Rescale the outcome or omit the baseline.")
        # A SciPy adapter reconstructs its test null only approximately. For a
        # nonzero or unknown null, evidence is relative to that null rather than
        # necessarily the sign of the original named group contrast.
        comparison_origin_is_zero = null == 0.0 and not source.startswith("scipy:")
        ctx = Context(ev, self.units, self.scope, self.better, baseline, self.outcome,
                      self.contrast, comparison_origin_is_zero, design=self.design, subgroup=self.subgroup)
        claims = build_claims(ctx)
        if null is not None and null != 0.0:
            claims.notes.insert(0, f"The effect is the difference from the test's null value {null:.12g} "
                                   f"(approximately reconstructed: {est:.12g} is {est + null:.12g} minus {null:.12g}).")
        return Result(plan=self, evidence=ev, context=ctx, claims=claims, source=source, null=null, label=label,
                      raw_input=raw or {})

    FINGERPRINT_VERSION = 2

    def _content(self, version: int = 2) -> dict:
        out = {
            "sesoi": list(self.sesoi) if self.sesoi else None,
            "sesoi_source": self.sesoi_source,
            "alpha": self.alpha,
            "interval_policy": self.interval_policy,
            "units": self.units,
            "scope": self.scope,
            "better": self.better,
        }
        if version >= 2:
            out["outcome"] = self.outcome
            out["contrast"] = self.contrast
            # added in 0.5.0; hashed only when given, so earlier plans keep their fingerprints
            if self.design is not None:
                out["design"] = self.design
            if self.subgroup is not None:
                out["subgroup"] = self.subgroup
        return out

    def fingerprint_for(self, version: int) -> str:
        """The fingerprint in an earlier format, to check a plan registered with an older release.

        Version 1 (statwarrant 0.2.0) hashed sesoi, sesoi_source, alpha, interval_policy,
        units, scope and better. Version 2 (0.3.0 on) also hashes outcome and contrast.
        """
        if version not in (1, 2):
            raise ValueError("fingerprint versions are 1 (0.2.0) and 2 (0.3.0 on)")
        blob = json.dumps(self._content(version), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def fingerprint(self) -> str:
        """SHA-256 of the plan's content (everything except the timestamp and registration link).

        ``declared_at`` is only your computer's clock and proves nothing. To make a
        declaration verifiable, register this fingerprint (or the plan JSON)
        somewhere a third party timestamps it -- OSF, AsPredicted, a public commit --
        before you see the result. Re-declaring the same plan gives the same fingerprint.
        """
        return self.fingerprint_for(self.FINGERPRINT_VERSION)

    def to_dict(self) -> dict:
        out = self._content()
        out["declared_at"] = self.declared_at
        out["fingerprint"] = self.fingerprint
        out["fingerprint_version"] = self.FINGERPRINT_VERSION
        out["registration"] = self.registration
        out["registration_verified"] = False
        return out


def _log_scale(units: Optional[str]) -> bool:
    """Units declaring a log scale (log-odds, log hazard ratio, logit, ln ...)."""
    return bool(units) and bool(re.search(r"\blog(?:arithm\w*)?\b|\blog[- ]|logit|\bln\b", units.lower()))


_DESIGNS = {"randomized": "randomised", "rct": "randomised", "randomised controlled trial": "randomised",
            "randomized controlled trial": "randomised", "randomised trial": "randomised",
            "randomized trial": "randomised", "cohort": "observational", "case control": "observational",
            "cross sectional": "observational", "observational study": "observational"}


def _half_unit(*xs: float) -> float:
    """Half a unit in the last printed decimal, assuming the numbers were printed to the same
    precision: the most decimals among them as written (0.83, 0.75, 0.93 -> 0.005; 4.2, 1.0,
    7.4 -> 0.05, since 1.0 cannot be told from 1)."""
    decimals = 0
    for x in xs:
        text = repr(float(x))
        if "e" in text or "E" in text:
            return 0.0
        if "." in text:
            decimals = max(decimals, len(text.split(".")[1].rstrip("0")))
    return 0.5 * 10.0 ** -decimals


def declare(
    *,
    sesoi: Optional[Union[Number, Tuple[Number, Number]]] = None,
    sesoi_source: Optional[str] = None,
    alpha: float = 0.05,
    interval_policy: str = "single",
    units: Optional[str] = None,
    scope: Optional[str] = None,
    better: str = "higher",
    outcome: Optional[str] = None,
    contrast: Optional[str] = None,
    registration: Optional[str] = None,
    design: Optional[str] = None,
    subgroup: Optional[str] = None,
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
        "standard" uses (1 - 2 alpha) for the equivalence test, as TOSTER does.
    units : str, optional
        Units of the effect, used in sentences ("points", "proportion", ...).
    scope : str, optional
        Population, data and conditions the result comes from. Attached to claims.
    better : {"higher", "lower"}
        Whether larger values of the outcome are better; used to read words like "improves".
    outcome, contrast : str, optional
        What was measured ("exam score") and what was compared ("new method minus
        existing method"). Your own description: reported, never verified.
    registration : str, optional
        Where the plan's fingerprint was registered (an OSF link, a commit URL). Not
        part of the fingerprint, so it can be added after registering.
    design : {"randomised", "observational"}, optional
        How the compared groups were formed. With "randomised", causal wording about an
        established average effect is not flagged; with "observational", it is a conflict.
        Your own description: reported, never verified.
    subgroup : str, optional
        When the result is itself a subgroup result ("patients on mechanical
        ventilation"): sentences naming that subgroup are not flagged as subgroup claims.
    """
    if interval_policy not in POLICIES:
        raise ValueError(f"interval_policy must be one of {POLICIES}")
    if better not in ("higher", "lower"):
        raise ValueError("better must be 'higher' or 'lower'")
    if not MIN_ALPHA <= alpha < 0.5:
        raise ValueError(f"alpha must be at least {MIN_ALPHA:g} and below 0.5")
    if design is not None:
        key = re.sub(r"[\s_-]+", " ", str(design).strip().lower())
        design = _DESIGNS.get(key, key)
        if design not in ("randomised", "observational"):
            raise ValueError("design must be 'randomised' (also 'randomized', 'rct') or 'observational' (also "
                             "'cohort', 'case-control', 'cross-sectional'), or omitted")
    if subgroup is not None and not str(subgroup).strip():
        raise ValueError("subgroup must be a non-empty description, or omitted")

    bounds = None
    if sesoi is not None:
        if not sesoi_source or not str(sesoi_source).strip():
            raise ValueError(
                "a smallest effect size of interest needs a stated reason: pass sesoi_source='...' "
                "(e.g. 'smallest change teachers consider worth acting on')"
            )
        if isinstance(sesoi, Numeric) or (isinstance(sesoi, np.ndarray) and sesoi.ndim == 0):
            value = checked_float(sesoi, "sesoi")
            if not (math.isfinite(value) and value > 0):
                raise ValueError("a single sesoi value must be a finite positive number; it means (-sesoi, +sesoi)")
            bounds = (-value, value)
        else:
            low, high = sesoi
            low = checked_float(low, "sesoi lower bound")
            high = checked_float(high, "sesoi upper bound")
            if not (math.isfinite(low) and math.isfinite(high) and low < 0 < high):
                raise ValueError("sesoi bounds must be finite and satisfy low < 0 < high")
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
        outcome=outcome,
        contrast=contrast,
        registration=registration,
        design=design,
        subgroup=None if subgroup is None else str(subgroup),
    )


@dataclass
class Result:
    plan: Plan
    evidence: Evidence
    context: Context
    claims: Claims
    source: str
    null: Optional[float] = 0.0
    label: Optional[str] = None
    raw_input: dict = field(default_factory=dict)
    checked: list = field(default_factory=list)
    _design: Optional[DesignTable] = field(default=None, repr=False)

    # ------------------------------------------------------------------ #
    def check(self, sentence: str, *, record: bool = True) -> CheckResult:
        """Look for possible problems in a sentence about this result (warnings only, never an approval).

        By default the sentence and its warnings are kept with the result and appear in
        ``to_dict()`` and ``to_markdown()``, so the report shows what you claimed.
        """
        res = replace(check_sentence(sentence, self.context), label=self.label)
        if record:
            self.checked.append(res)
        return res

    @property
    def thresholds(self) -> Thresholds:
        """Decisions for every symmetric threshold at once."""
        return self.evidence.thresholds()

    def not_verified(self) -> list:
        """What statwarrant does not check, for this result."""
        items = [
            "That the outcome, contrast and scope descriptions are accurate: they are your own text.",
            "Whether the design supports causal claims (randomisation, confounding).",
            "Whether the result generalises beyond the declared scope.",
            "Whether the model behind the estimate and standard error is appropriate "
            "(statwarrant assumes a normal or t reference distribution).",
            "Data quality and the analysis choices made before the estimate.",
            "Units and conversions in checked sentences: unit checks are pattern-based and partial; "
            "units and conversions may be unchecked and need independent review.",
        ]
        items.append("That the plan was declared before the data were seen. The fingerprint is evidence only if it was "
                     "registered with a third party before the analysis.")
        if self.plan.registration:
            items.append("The registration reference is your own text: statwarrant does not check that it exists, "
                         "when it was made, or that it records this plan's fingerprint "
                         f"({self.plan.fingerprint[:16]}…).")
        return items

    def design(self, assumed_effects: Sequence[float], *, source: str) -> DesignTable:
        """Power, Type S and exaggeration ratio of this design under assumed true effects."""
        ev = self.evidence
        self._design = design_table(assumed_effects, ev.se, self.plan.alpha, source, ev.estimate, ev.df)
        return self._design

    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        th = self.thresholds
        out = {
            "schema": SCHEMA,
            "statwarrant_version": __version__,
            "label": self.label,
            "plan": self.plan.to_dict(),
            "input": self.source,
            "raw_input": self.raw_input,
            "null_value": self.null,
            "evidence": self.evidence.to_dict(),
            "thresholds": dict(th.to_dict(), declared_threshold=self._declared_position()),
            "claims": self.claims.to_dict(),
            "checked_sentences": [c.to_dict() for c in self.checked],
            "not_verified": self.not_verified(),
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
        kwargs.setdefault("allow_nan", False)
        return json.dumps(self.to_dict(), **kwargs)

    def _declared_position(self) -> Optional[str]:
        sesoi = self.plan.sesoi
        if sesoi is None or -sesoi[0] != sesoi[1]:
            return None  # asymmetric bounds: the symmetric cut-offs do not apply
        return self.thresholds.decision(sesoi[1])

    def _threshold_lines(self) -> list:
        th = self.thresholds
        u = f" {self.plan.units}" if self.plan.units else ""
        out = []
        if th.met_below is None:
            out.append("- No positive threshold gives an effect beyond it: the difference from zero is not "
                       "established at the declared significance level.")
        else:
            out.append(f"- An effect larger than ±d is established for every threshold d below "
                       f"**{fmt_down(th.met_below)}{u}** ({level_text(th.met_level)} interval; cut-off about "
                       f"{th.met_below:.6g}).")
        out.append(f"- Equivalence within ±d is established for every threshold d above "
                   f"**{fmt_up(th.equivalence_above)}{u}** ({level_text(th.equivalence_level)} interval; "
                   f"cut-off about {th.equivalence_above:.6g}).")
        if th.met_below is not None:
            out.append(f"- For thresholds from {th.met_below!r} to {th.equivalence_above!r} (the exact cut-offs, "
                       f"both included), neither is established.")
        else:
            out.append(f"- For thresholds up to {th.equivalence_above!r} (the exact cut-off, included), "
                       f"equivalence is not established.")
        pos = self._declared_position()
        if pos is not None:
            words = {"exceeds": "the effect exceeds it", "equivalent": "equivalence is established",
                     "undetermined": "neither is established"}[pos]
            out.append(f"- Your declared threshold (±{fmt_bound(self.plan.sesoi[1])}{u}): {words}.")
        elif self.plan.sesoi is not None:
            out.append("- Your declared bounds are asymmetric; see the tests above.")
        return out

    def to_markdown(self) -> str:
        ev = self.evidence
        p = self.plan
        title = "## statwarrant report" + (f": {self.label}" if self.label else "")
        lines = [title, ""]
        lines.append("### What was compared (your description, not verified)")
        lines.append(f"- **Outcome:** {p.outcome or 'not stated'}")
        lines.append(f"- **Contrast:** {p.contrast or 'not stated'}")
        lines.append(f"- **Scope:** {p.scope or 'not stated'}")
        lines.append(f"- **Input:** {self.source}")
        lines += ["", "### Declared plan (timing not verified)"]
        if p.sesoi:
            lines.append(f"- **Smallest effect size of interest:** {fmt_bounds(*p.sesoi)}, "
                         f"because: {p.sesoi_source}")
        else:
            lines.append("- **Smallest effect size of interest:** none declared")
        lines.append(f"- **Alpha:** {p.alpha}; **interval policy:** {p.interval_policy}")
        lines.append(f"- **Plan fingerprint (v{p.FINGERPRINT_VERSION}):** `{p.fingerprint[:16]}`")
        lines.append(f"- **Registration (your reference, not verified):** "
                     f"{p.registration or 'none given; the fingerprint alone proves nothing'}")
        lines += ["", "### Result", ""]
        lines.append(f"Estimate {fmt(ev.estimate)}{' ' + p.units if p.units else ''} (SE {fmt(ev.se)}"
                     f"{'' if ev.df is None else f', df {fmt(ev.df)}'}).")
        lines += ["", "| Test | Interval | p-value | Decision |", "| --- | --- | --- | --- |"]
        lo, hi = ev.zero_interval
        lines.append(f"| Differs from zero | {level_text(ev.zero_level)} {fmt_ci(lo, hi)} | {fmt_p(ev.p_zero)} | "
                     f"{'yes' if ev.differs_from_zero else 'not established'} |")
        if p.sesoi:
            elo, ehi = ev.equivalence_interval
            mlo, mhi = ev.met_interval
            lines.append(f"| Equivalent (TOST) | {level_text(ev.equivalence_level)} {fmt_ci(elo, ehi)} | "
                         f"{fmt_p(ev.p_equivalence)} (one-sided, vs {fmt(ev.equivalence_threshold)}) | "
                         f"{'yes' if ev.equivalent else 'not established'} |")
            lines.append(f"| Exceeds SESOI (MET) | {level_text(ev.met_level)} {fmt_ci(mlo, mhi)} | "
                         f"{fmt_p(ev.p_minimal_effect)} (one-sided, vs {fmt(ev.met_threshold)}) | "
                         f"{'yes' if ev.exceeds_sesoi else 'not established'} |")
        lines += ["", "### Every threshold at once", ""]
        lines.append("Computed from the same estimate and standard error, not new tests. Decisions use test-statistic "
                     "arithmetic, not rounded display endpoints. Choosing a threshold after seeing these numbers "
                     "is not a confirmatory claim.")
        lines.append("")
        lines += self._threshold_lines()
        lines += ["", "### You can say"]
        lines += [f"- {c.text}" for c in self.claims.allowed]
        lines += ["", "### Do not say"]
        lines += [f"- ~~{c.text}~~ {c.reason}" for c in self.claims.blocked]
        if self.claims.notes:
            lines += ["", "### Notes"] + [f"- {n}" for n in self.claims.notes]
        if self.checked:
            lines += ["", "### Sentences checked",
                      "These sentences are stored in the report. Remove them before sharing if they are "
                      "confidential, or check with `record=False`.", ""]
            for c in self.checked:
                head = {"warnings": f"{len(c.warnings)} warning(s)", "no_warnings": "no warnings (not a clearance)",
                        "no_supported_pattern": "no supported pattern detected"}[c.status]
                lines.append(f"- \"{c.sentence}\": {head}")
                lines += [f"  - {w.status}, {w.rule}, \"{w.text}\": {w.reason}" for w in c.warnings]
                if c.unchecked:
                    lines.append("  - not checked: " + ", ".join(f"\"{u}\"" for u in c.unchecked))
        lines += ["", "### Not verified by statwarrant"] + [f"- {n}" for n in self.not_verified()]
        if self._design is not None:
            lines += ["", self._design.to_markdown()]
        return "\n".join(lines)

    def __str__(self) -> str:
        parts = [c.text for c in self.claims.allowed]
        if self.claims.blocked:
            parts.append("Do not say: " + "; ".join(f"\"{c.text}\"" for c in self.claims.blocked))
        parts += self.claims.notes
        th = self.thresholds
        u = f" {self.plan.units}" if self.plan.units else ""
        line = (f"Every threshold: equivalence within ±d for any d above {fmt_up(th.equivalence_above)}{u}; "
                f"not for d up to {th.equivalence_above!r}")
        if th.met_below is not None:
            line = (f"Every threshold: an effect beyond ±d for any d below {fmt_down(th.met_below)}{u}; "
                    f"equivalence within ±d for any d above {fmt_up(th.equivalence_above)}{u}; neither from "
                    f"{th.met_below!r} to {th.equivalence_above!r} (exact cut-offs)")
        parts.append(line + ".")
        return "\n".join(parts)
