"""Structured assertions: a claim written as fields, judged against the result.

A sentence can be read in many ways; an assertion cannot. ``Assertion`` states one
claim about the effect (its kind, direction, size) and :meth:`Result.verify` judges it
with the same tests the claim contract uses. Nothing here reads natural language:
a person, a language model (see :mod:`statwarrant.llm`) or an AI assistant connected
through the MCP server (see :mod:`statwarrant.mcp_server`) turns a sentence into
assertions, and statwarrant decides.

A verdict concerns the statistical proposition only. It never approves the wording,
scope, causal story or meaning of the sentence it came from.

Directions refer to the sign of the declared contrast: with contrast "A minus B",
"positive" means A is larger than B. Sizes are in the declared units and on the scale
of the analysis (log ratios for ``ratio=True``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from ._core import level_text
from .claims import Context, fmt, fmt_bounds, fmt_ci

#: kinds of claims that can be judged
KINDS = {
    "nonzero": "the effect differs from zero (is statistically significant)",
    "no_effect": "there is no effect, no difference, or the effect is zero",
    "equivalent": "the effect is practically equivalent to zero or negligible (within the SESOI bounds)",
    "important": "the effect is practically important (beyond the smallest effect size of interest)",
    "at_least": "the effect is at least (more than, over) a stated size",
    "at_most": "the effect is at most (less than, under) a stated size",
    "about": "the effect is about (approximately) a stated size",
    "causal": "the treatment or factor caused the effect",
    "generalization": "the effect holds beyond the population, data or conditions studied, or for every individual",
}

DIRECTIONS = ("positive", "negative")
POLARITIES = ("asserted", "denied", "hedged")

#: verdicts. "supported" concerns the statistical proposition only, never the sentence.
SUPPORTED = "supported"
NOT_ESTABLISHED = "not_established"
CONTRADICTED = "contradicted"
TO_VERIFY = "to_verify"
STATUSES = (SUPPORTED, NOT_ESTABLISHED, CONTRADICTED, TO_VERIFY)


@dataclass(frozen=True)
class Assertion:
    """One claim about the effect.

    kind : one of :data:`KINDS`.
    direction : "positive", "negative" (sign of the declared contrast) or None.
    value : a size in the declared units, for "at_least", "at_most" and "about".
    polarity : "asserted" (default), "denied" ("not significant") or "hedged" ("may be").
    quote : the words the assertion was read from, kept for the report.
    """

    kind: str
    direction: Optional[str] = None
    value: Optional[float] = None
    polarity: str = "asserted"
    quote: Optional[str] = None

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {sorted(KINDS)}, got {self.kind!r}")
        if self.direction is not None and self.direction not in DIRECTIONS:
            raise ValueError(f"direction must be 'positive', 'negative' or None, got {self.direction!r}")
        if self.polarity not in POLARITIES:
            raise ValueError(f"polarity must be one of {POLARITIES}, got {self.polarity!r}")
        if self.kind in ("at_least", "at_most", "about"):
            if self.value is None:
                raise ValueError(f"an {self.kind!r} assertion needs value=")
            v = float(self.value)
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError("value must be a finite number")
            object.__setattr__(self, "value", v)
        elif self.value is not None:
            object.__setattr__(self, "value", float(self.value))

    @classmethod
    def from_dict(cls, d: dict) -> "Assertion":
        direction = d.get("direction")
        if direction in ("", "none", "null", "unclear"):
            direction = None
        value = d.get("value")
        return cls(kind=str(d.get("kind", "")).strip(), direction=direction,
                   value=None if value in (None, "") else float(value),
                   polarity=str(d.get("polarity") or "asserted"), quote=d.get("quote"))

    def to_dict(self) -> dict:
        return {"kind": self.kind, "direction": self.direction, "value": self.value,
                "polarity": self.polarity, "quote": self.quote}


@dataclass(frozen=True)
class Verdict:
    """How one assertion fares against the result. Never an approval of a sentence."""

    assertion: Assertion
    status: str
    reason: str

    def to_dict(self) -> dict:
        return {"assertion": self.assertion.to_dict(), "status": self.status, "reason": self.reason}


def _sign(direction: Optional[str]) -> int:
    return {"positive": 1, "negative": -1}.get(direction or "", 0)


def _u(ctx: Context, x: float) -> str:
    return ctx.u(x)


def _judge(a: Assertion, ctx: Context):
    """(status, reason) for an asserted claim."""
    ev = ctx.evidence
    z = ctx.ci_text()
    lo, hi = ev.zero_interval
    s = _sign(a.direction)

    if a.kind == "nonzero":
        if not ev.differs_from_zero:
            return NOT_ESTABLISHED, f"A difference from zero is not established ({z}, p = {fmt(ev.p_zero)})."
        if s and s != ev.direction:
            return CONTRADICTED, f"An effect is established, in the opposite direction ({z})."
        return SUPPORTED, f"The zero test rejects ({z}, p = {fmt(ev.p_zero)})."

    if a.kind == "no_effect":
        if ev.differs_from_zero:
            return CONTRADICTED, f"An effect different from zero is established ({z})."
        if ev.equivalent:
            return NOT_ESTABLISHED, (
                f"An effect of exactly zero cannot be shown. Equivalence within {fmt_bounds(*ev.sesoi)} is "
                f"established ({ctx.ci_text('equivalence')}); say that instead.")
        return NOT_ESTABLISHED, (f"A non-significant result is not evidence of no effect: the data are compatible "
                                 f"with effects from {_u(ctx, lo)} to {_u(ctx, hi)} ({z}).")

    if a.kind in ("equivalent", "important"):
        if ev.sesoi is None:
            return NOT_ESTABLISHED, ("No smallest effect size of interest was declared, so practical importance "
                                     "or equivalence cannot be judged.")
        bounds = fmt_bounds(*ev.sesoi)
        if a.kind == "equivalent":
            e = ctx.ci_text("equivalence")
            if ev.equivalent:
                return SUPPORTED, f"The equivalence test establishes an effect within {bounds} ({e})."
            if ev.exceeds_sesoi:
                return CONTRADICTED, f"The effect exceeds the smallest effect size of interest ({ctx.ci_text('met')})."
            return NOT_ESTABLISHED, f"Equivalence within {bounds} is not established ({e})."
        m = ctx.ci_text("met")
        if ev.exceeds_sesoi:
            if s and s != ev.direction:
                return CONTRADICTED, f"The effect exceeds the bounds {bounds}, in the opposite direction ({m})."
            return SUPPORTED, f"The minimal-effect test establishes an effect beyond {bounds} ({m})."
        if ev.equivalent:
            return CONTRADICTED, (f"The equivalence test establishes an effect within {bounds} "
                                  f"({ctx.ci_text('equivalence')}).")
        return NOT_ESTABLISHED, f"An effect beyond {bounds} is not established ({m})."

    if a.kind in ("at_least", "at_most"):
        v = abs(a.value)
        if s == 0:  # a bound on the size, either direction
            if a.kind == "at_least":
                if lo > v or hi < -v:
                    return SUPPORTED, f"The {z} lies beyond ±{fmt(v)}."
                if -v < lo and hi < v:
                    return CONTRADICTED, f"The {z} lies within ±{fmt(v)}: effects of that size are ruled out."
                return NOT_ESTABLISHED, f"An effect of at least {fmt(v)} in size is not established ({z})."
            if -v < lo and hi < v:
                return SUPPORTED, f"The {z} lies within ±{fmt(v)}."
            if lo > v or hi < -v:
                return CONTRADICTED, f"The {z} lies beyond ±{fmt(v)}."
            return NOT_ESTABLISHED, f"An effect of at most {fmt(v)} in size is not established ({z})."
        # signed: "A exceeds B by at least v" is theta >= v (or theta <= -v for negative)
        near, far = (lo, hi) if s > 0 else (-hi, -lo)
        if a.kind == "at_least":
            if near > v:
                return SUPPORTED, f"The whole {z} lies beyond {fmt(s * v)}."
            if far < v:
                return CONTRADICTED, f"The {z} rules out an effect of {fmt(s * v)} or more in that direction."
            return NOT_ESTABLISHED, f"An effect of at least {fmt(s * v)} is not established ({z})."
        if far < v:
            return SUPPORTED, f"The {z} rules out effects beyond {fmt(s * v)} in that direction."
        if near > v:
            return CONTRADICTED, f"The whole {z} lies beyond {fmt(s * v)}."
        return NOT_ESTABLISHED, f"An effect of at most {fmt(s * v)} is not established ({z})."

    if a.kind == "about":
        v = a.value if not s else s * abs(a.value)
        if lo <= v <= hi:
            return TO_VERIFY, (f"{fmt(v)} lies inside the {z}; the point estimate is {fmt(ev.estimate)}. A single "
                               f"value is a description, not a finding: report the interval with it.")
        return CONTRADICTED, f"{fmt(v)} lies outside the {z}."

    if a.kind == "causal":
        if not ev.differs_from_zero:
            return NOT_ESTABLISHED, f"Even an association is not established ({z})."
        if ctx.design == "observational":
            return CONTRADICTED, "The design was declared observational: a causal effect is not shown by these data."
        if ctx.design == "randomised":
            return TO_VERIFY, ("The design was declared randomised (your description, not verified). Check that "
                               "the cause and outcome named match the randomised comparison.")
        return TO_VERIFY, "No design was declared; whether the comparison supports a causal claim is not known."

    if a.kind == "generalization":
        where = f"'{ctx.scope}' only" if ctx.scope else "the data analysed only"
        return NOT_ESTABLISHED, (f"The evidence comes from {where}; an average effect does not show that every "
                                 f"individual or setting is affected.")

    raise KeyError(a.kind)


def verify(assertion: Union[Assertion, dict], ctx: Context) -> Verdict:
    """Judge one assertion against a result's context. See :meth:`Result.verify`."""
    a = assertion if isinstance(assertion, Assertion) else Assertion.from_dict(assertion)
    status, reason = _judge(a, ctx)
    if a.polarity == "asserted":
        return Verdict(a, status, reason)
    # Denials and hedges are never cleared; denying an established finding is a conflict.
    if status == SUPPORTED:
        word = "denies" if a.polarity == "denied" else "hedges on"
        return Verdict(a, CONTRADICTED, f"The sentence {word} something the result establishes: {reason}")
    return Verdict(a, TO_VERIFY, f"Stated as {a.polarity}; check the wording against the result: {reason}")


def describe_levels(ctx: Context) -> str:
    """The interval levels a verdict can cite, for prompts and reports."""
    ev = ctx.evidence
    out = [f"zero test {level_text(ev.zero_level)} {fmt_ci(*ev.zero_interval)}"]
    if ev.equivalence_interval is not None:
        out.append(f"equivalence {level_text(ev.equivalence_level)} {fmt_ci(*ev.equivalence_interval)}")
    if ev.met_interval is not None and ev.met_method == "relevance":
        out.append(f"minimal effect {level_text(ev.met_level)} {fmt_ci(*ev.met_interval)}")
    return "; ".join(out)
