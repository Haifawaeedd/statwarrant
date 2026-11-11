"""The claim contract: which statements a result supports, and which it does not.

Two entry points share one judge, so they can never disagree:

* :func:`build_claims` lists the allowed statements for a result (templates with
  the numbers filled in) and a catalogue of common statements that are blocked,
  each with a reason.
* :func:`check_sentence` judges a sentence the researcher wrote.

The sentence checker is deliberately simple. It matches a fixed set of English
claim patterns (no effect, equivalence, practical importance, direction,
significance, generalisation, certainty, percentages). A sentence that matches
none of them is returned as ``"unrecognized"`` rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ._core import Evidence

ALLOWED = "allowed"
BLOCKED = "blocked"
CAUTION = "needs_care"
UNRECOGNIZED = "unrecognized"


def fmt(x: float) -> str:
    """Compact number formatting for claim text."""
    if x == 0:
        return "0"
    s = format(x, ".3g")
    return "0" if s in ("-0", "0") else s


@dataclass(frozen=True)
class Claim:
    text: str
    status: str
    reason: str = ""
    category: str = ""

    def to_dict(self) -> dict:
        return {"text": self.text, "status": self.status, "reason": self.reason, "category": self.category}


@dataclass
class Claims:
    allowed: List[Claim] = field(default_factory=list)
    blocked: List[Claim] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "allowed": [c.to_dict() for c in self.allowed],
            "blocked": [c.to_dict() for c in self.blocked],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class CheckResult:
    """Verdict on one sentence."""

    sentence: str
    verdict: str
    categories: tuple
    reasons: tuple

    def __str__(self) -> str:
        head = f"[{self.verdict.upper()}] {self.sentence}"
        if not self.reasons:
            return head
        return head + "\n" + "\n".join(f"  - {r}" for r in self.reasons)

    def to_dict(self) -> dict:
        return {
            "sentence": self.sentence,
            "verdict": self.verdict,
            "categories": list(self.categories),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class Context:
    """Everything the judge needs besides the sentence."""

    evidence: Evidence
    units: Optional[str] = None
    scope: Optional[str] = None
    better: str = "higher"
    baseline: Optional[float] = None

    def u(self, x: float) -> str:
        return f"{fmt(x)} {self.units}" if self.units else fmt(x)

    def ci_text(self, which: str = "zero") -> str:
        ev = self.evidence
        if which == "bounds" and ev.bounds_interval is not None:
            lo, hi = ev.bounds_interval
            level = ev.bounds_level
        else:
            lo, hi = ev.zero_interval
            level = ev.zero_level
        return f"{level:.0%} CI [{fmt(lo)}, {fmt(hi)}]"


# --------------------------------------------------------------------------- #
# Patterns. Order matters: more specific phrasings are tested first and, once
# matched, mask the words they used so a later, broader pattern cannot re-read
# them (e.g. "no meaningful difference" must not also count as "meaningful").
# --------------------------------------------------------------------------- #

_EFFECT_NOUNS = r"(effect|difference|differences|impact|association|relationship|change|improvement|benefit|gain)"
_EFFECT_VERBS = r"(affect|change|differ|improve|increase|decrease|reduce|influence|help|matter|work)"

PATTERNS = [
    ("evidence_absent", re.compile(r"\bno (clear |strong |statistical )?evidence (of|for|that)\b")),
    ("nonsignificance", re.compile(
        r"\b(not (statistically )?significant(ly)?|no (statistically )?significant|non-?significant|"
        r"did not reach (statistical )?significance|failed to reach (statistical )?significance|"
        r"was not significant|were not significant)\b")),
    ("equivalence", re.compile(
        r"\b(equivalent|comparable|on par|as (good|effective|accurate) as|"
        r"no (meaningful|practical|practically important|important|relevant) differences?|"
        r"(similar|the same) (performance|results|outcomes|effects?|accuracy)|"
        r"perform(s|ed)? (similarly|the same|equally))\b")),
    ("no_effect", re.compile(
        r"\b(no " + _EFFECT_NOUNS + r"|(did|does|do|was|were|is|are|had|has) not " + _EFFECT_VERBS +
        r"|(has|had|have|shows?|showed) no " + _EFFECT_NOUNS + r"|there (is|was|were) no " + _EFFECT_NOUNS +
        r"|(does|did|do)n't " + _EFFECT_VERBS + r"|not (any )?different|no different)\b")),
    ("certainty", re.compile(r"\b(prove[sdn]?|proof|conclusively|definitely|certainly|undeniabl[ey]|exactly|precisely)\b")),
    ("generalization", re.compile(
        r"\b(in general|generally|always|universally|for everyone|for all\b|all (students|users|patients|people|participants|models|tasks|datasets|settings)|"
        r"generali[sz]es?|in every|across all|regardless of)\b")),
    ("importance", re.compile(
        r"\b(meaningful(ly)?|substantial(ly)?|important|large|practically significant|clinically (significant|relevant|meaningful)|"
        r"dramatic(ally)?|strong(ly)?|considerabl[ey]|marked(ly)?|major|big|huge|sizable)\b")),
    ("significance", re.compile(r"\b(statistically )?significant(ly)?\b")),
    ("increase", re.compile(r"\b(increase[sd]?|increasing|higher|raise[sd]?|rose|grew|grows)\b")),
    ("decrease", re.compile(r"\b(decrease[sd]?|decreasing|lower|fewer|reduce[sd]?|reduction|dropped|declined?)\b")),
    ("better", re.compile(r"\b(improve[sd]?|improvement|improving|better|outperform(s|ed)?|superior|beats?|gains?)\b")),
    ("worse", re.compile(r"\b(worse|worsen(s|ed)?|harm(s|ed|ful)?|inferior|underperform(s|ed)?|hurts?)\b")),
    ("percentage", re.compile(r"\d+(\.\d+)?\s*(%|percent\b|per cent\b)")),
]


def _match_categories(sentence: str) -> List[str]:
    text = " " + sentence.lower() + " "
    found: List[str] = []
    for name, pat in PATTERNS:
        if pat.search(text):
            found.append(name)
            text = pat.sub(lambda m: " " * len(m.group(0)), text)
    # A negated or equivalence statement already speaks about direction; drop
    # the direction words it contained so they are not judged twice.
    if {"no_effect", "nonsignificance", "evidence_absent", "equivalence"} & set(found):
        found = [c for c in found if c not in ("increase", "decrease", "better", "worse")]
    return found


def _claimed_sign(categories: List[str], better: str) -> Optional[int]:
    signs = set()
    if "increase" in categories:
        signs.add(1)
    if "decrease" in categories:
        signs.add(-1)
    good = 1 if better == "higher" else -1
    if "better" in categories:
        signs.add(good)
    if "worse" in categories:
        signs.add(-good)
    if len(signs) == 1:
        return signs.pop()
    return None if not signs else 0  # 0 = mixed / contradictory direction words


def _judge(cat: str, ctx: Context, sign: Optional[int]) -> tuple:
    """Return (status, reason) for one claim category."""
    ev = ctx.evidence
    has_sesoi = ev.sesoi is not None
    lo, hi = ev.zero_interval
    scope = ctx.scope

    if cat == "no_effect":
        if ev.differs_from_zero:
            return BLOCKED, f"The data show an effect different from zero ({ctx.ci_text()})."
        if ev.equivalent:
            low, high = ev.sesoi
            return BLOCKED, (
                f"Equivalence rules out effects outside [{fmt(low)}, {fmt(high)}], not every effect. "
                f"Say the effect is practically equivalent within these bounds."
            )
        return BLOCKED, (
            f"A non-significant result is not evidence of no effect: the data are compatible with "
            f"effects from {ctx.u(lo)} to {ctx.u(hi)} ({ctx.ci_text()})."
        )

    if cat in ("nonsignificance", "evidence_absent"):
        if ev.differs_from_zero:
            return BLOCKED, f"The result is statistically significant ({ctx.ci_text()}, p = {fmt(ev.p_zero)})."
        return CAUTION, (
            f"Literally true, but readers often take it to mean 'no effect'. Add the interval: "
            f"effects from {ctx.u(lo)} to {ctx.u(hi)} remain compatible with the data."
        )

    if cat == "equivalence":
        if not has_sesoi:
            return BLOCKED, "No smallest effect size of interest was declared, so equivalence cannot be assessed."
        low, high = ev.sesoi
        if ev.equivalent:
            return ALLOWED, f"Effects outside [{fmt(low)}, {fmt(high)}] are rejected ({ctx.ci_text('bounds')})."
        return BLOCKED, (
            f"Equivalence is not established: the {ctx.ci_text('bounds')} is not inside "
            f"[{fmt(low)}, {fmt(high)}]."
        )

    if cat == "importance":
        if not has_sesoi:
            return BLOCKED, "No smallest effect size of interest was declared, so practical importance cannot be assessed."
        low, high = ev.sesoi
        if ev.exceeds_sesoi:
            if sign is not None and sign != 0 and sign != ev.direction:
                return BLOCKED, "The effect is practically important, but in the opposite direction to the one stated."
            return ALLOWED, f"The whole {ctx.ci_text('bounds')} lies beyond the smallest effect size of interest."
        return BLOCKED, (
            f"The {ctx.ci_text('bounds')} includes values smaller than the smallest effect size of interest "
            f"([{fmt(low)}, {fmt(high)}])."
        )

    if cat == "significance":
        if not ev.differs_from_zero:
            return BLOCKED, f"The difference from zero is not statistically significant ({ctx.ci_text()}, p = {fmt(ev.p_zero)})."
        if sign is not None and sign != 0 and sign != ev.direction:
            return BLOCKED, "The result is significant, but in the opposite direction to the one stated."
        return ALLOWED, f"{ctx.ci_text()} excludes zero (p = {fmt(ev.p_zero)})."

    if cat == "direction":
        if sign == 0:
            return BLOCKED, "The sentence states both directions at once."
        if ev.direction == 0:
            return BLOCKED, f"The direction of the effect is not established: {ctx.ci_text()} includes zero."
        if sign != ev.direction:
            return BLOCKED, f"The data point the other way ({ctx.ci_text()})."
        return ALLOWED, f"The direction is established ({ctx.ci_text()})."

    if cat == "generalization":
        where = f"'{scope}'" if scope else "the setting that was studied (no scope was declared)"
        return BLOCKED, f"The evidence comes from {where} only; it does not show the effect holds beyond it."

    if cat == "certainty":
        return BLOCKED, (
            f"Statistics does not prove, and the estimate is uncertain: report the interval "
            f"({ctx.ci_text()}), not a single exact value."
        )

    if cat == "percentage":
        if ctx.baseline:
            rel = ev.estimate / ctx.baseline
            return CAUTION, (
                f"Say whether this is an absolute or a relative change, and report both: "
                f"absolute {ctx.u(ev.estimate)}, relative {rel:+.1%} of the baseline {ctx.u(ctx.baseline)}."
            )
        return CAUTION, (
            "Say whether this is percentage points (absolute) or a relative change, and report both; "
            "declare a baseline to get both numbers."
        )

    raise KeyError(cat)


_DIRECTION_WORDS = ("increase", "decrease", "better", "worse")


def check_sentence(sentence: str, ctx: Context) -> CheckResult:
    """Judge one English sentence against the result."""
    cats = _match_categories(sentence)
    sign = _claimed_sign(cats, ctx.better)
    has_direction = any(c in _DIRECTION_WORDS for c in cats)
    folded = "importance" in cats or "significance" in cats

    judged = []
    reasons = []
    for cat in cats:
        if cat in _DIRECTION_WORDS:
            continue
        status, reason = _judge(cat, ctx, sign)
        judged.append((cat, status))
        reasons.append(reason)

    # Direction words are judged on their own unless importance or significance
    # already checked the stated sign; contradictory words are always flagged.
    if has_direction and (not folded or sign == 0):
        status, reason = _judge("direction", ctx, sign)
        judged.append(("direction", status))
        reasons.append(reason)

    if not judged:
        return CheckResult(sentence, UNRECOGNIZED, (), (
            "No known claim pattern found. statwarrant 0.1 recognises English statements about "
            "no effect, equivalence, importance, direction, significance, generalisation, certainty "
            "and percentages.",
        ))
    statuses = {s for _, s in judged}
    if BLOCKED in statuses:
        verdict = BLOCKED
    elif CAUTION in statuses:
        verdict = CAUTION
    else:
        verdict = ALLOWED
    return CheckResult(sentence, verdict, tuple(n for n, _ in judged), tuple(reasons))


# --------------------------------------------------------------------------- #
# The contract
# --------------------------------------------------------------------------- #

_CATALOGUE = [
    "There is no effect.",
    "The effect is practically important.",
    "The two conditions are equivalent.",
    "The effect is statistically significant.",
    "The effect generalizes to all settings.",
    "The results prove the effect is exactly the estimated value.",
]


def _allowed_templates(ctx: Context) -> List[str]:
    ev = ctx.evidence
    lo, hi = ev.zero_interval
    where = ""
    cls = ev.claim_class
    if ev.sesoi is not None:
        low, high = ev.sesoi
        b = ctx.ci_text("bounds")
    z = ctx.ci_text()

    if cls == "differs_positive":
        return [f"The effect is positive{where} ({z}). Its practical importance cannot be judged without a declared smallest effect size of interest."]
    if cls == "differs_negative":
        return [f"The effect is negative{where} ({z}). Its practical importance cannot be judged without a declared smallest effect size of interest."]
    if cls == "inconclusive_no_sesoi":
        return [f"A difference from zero is not established{where}; the data are compatible with effects from {ctx.u(lo)} to {ctx.u(hi)} ({z})."]
    if cls == "exceeds_sesoi_positive":
        return [f"The effect is positive and larger than the smallest effect size of interest ({ctx.u(high)}){where} ({b})."]
    if cls == "exceeds_sesoi_negative":
        return [f"The effect is negative and larger in magnitude than the smallest effect size of interest ({ctx.u(low)}){where} ({b})."]
    if cls == "nonzero_negligible":
        return [f"The effect differs from zero but is smaller than the smallest effect size of interest{where}: "
                f"it lies within [{fmt(low)}, {fmt(high)}] ({b}). It is detectable but practically negligible."]
    if cls == "equivalent":
        return [f"The effect is practically equivalent to zero within [{fmt(low)}, {fmt(high)}]{where} ({b}). "
                f"A small effect inside these bounds is not ruled out."]
    if cls == "positive_importance_undetermined":
        return [f"The effect is positive{where} ({z}); whether it reaches the smallest effect size of interest "
                f"({ctx.u(high)}) is not determined by these data."]
    if cls == "negative_importance_undetermined":
        return [f"The effect is negative{where} ({z}); whether it reaches the smallest effect size of interest "
                f"({ctx.u(low)}) is not determined by these data."]
    if cls == "inconclusive_one_side":
        return [f"The result is inconclusive{where}: the data are compatible with an effect of zero and with an "
                f"effect beyond the smallest effect size of interest ({b})."]
    if cls == "inconclusive_both":
        return [f"The result is inconclusive{where}: the data are compatible with an effect of zero and with "
                f"effects beyond the smallest effect size of interest in either direction ({b})."]
    raise KeyError(cls)


def build_claims(ctx: Context) -> Claims:
    claims = Claims()
    for text in _allowed_templates(ctx):
        if ctx.scope:
            text = f"{text} Scope: {ctx.scope}."
        claims.allowed.append(Claim(text, ALLOWED, "Matches the position of the interval.", ctx.evidence.claim_class))
    for sentence in _CATALOGUE:
        res = check_sentence(sentence, ctx)
        if res.verdict == BLOCKED:
            claims.blocked.append(Claim(sentence, BLOCKED, " ".join(res.reasons), ",".join(res.categories)))

    ev = ctx.evidence
    if ev.level_conflict:
        claims.notes.append(
            f"Level conflict: at the {ev.bounds_level:.0%} level used for the threshold test the effect exceeds "
            f"the smallest effect size of interest, but at the {ev.zero_level:.0%} level used for the zero test a "
            f"difference from zero is not established. The two decisions use different intervals. "
            f"Use interval_policy='single' for one consistent reading."
        )
    if ev.sesoi is None:
        claims.notes.append("No smallest effect size of interest was declared: claims about practical importance "
                            "and equivalence are withheld.")
    if not ctx.scope:
        claims.notes.append("No scope was declared: state the population, data and conditions the result comes from.")
    if ctx.baseline:
        rel = ev.estimate / ctx.baseline
        claims.notes.append(
            f"Report both scales: absolute change {ctx.u(ev.estimate)}, relative change {rel:+.1%} "
            f"of the baseline {ctx.u(ctx.baseline)}."
        )
    return claims
