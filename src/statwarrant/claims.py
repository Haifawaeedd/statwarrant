"""The claim contract and the sentence linter.

Two entry points share one judge, so they can never disagree:

* :func:`build_claims` lists the statements a result supports (templates with the
  numbers filled in, generated from the result itself) and a catalogue of common
  statements that conflict with it, each with a reason.
* :func:`check_sentence` looks for possible problems in a sentence the researcher
  wrote. It is a warnings-only linter: it never approves a sentence.

The linter matches a fixed set of English patterns. For each recognised part it
reports one of:

* ``conflict``: the part appears to contradict the result;
* ``check``: the part cannot be verified against the result and needs a human;
* ``consistent``: the part agrees with the result.

A sentence gets the status ``warnings`` (at least one conflict or check),
``no_warnings`` (only consistent parts) or ``no_supported_pattern``. ``no_warnings``
is not a clearance: everything outside the recognised parts, listed in
``CheckResult.unchecked``, was not checked. A warning is a prompt for review, not
proof that the sentence is false.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from ._core import Evidence, level_text

CONSISTENT = "consistent"
CHECK = "check"
CONFLICT = "conflict"

_RANK = {CONSISTENT: 0, CHECK: 1, CONFLICT: 2}


def fmt(x: float) -> str:
    """Compact number formatting for claim text."""
    if x == 0:
        return "0"
    s = format(x, ".3g")
    return "0" if s in ("-0", "0") else s


def fmt_bound(x: float) -> str:
    """Shortest readable decimal that round-trips to the declared binary64 value."""
    s = repr(float(x)).replace("e+", "e")
    return s[:-2] if s.endswith(".0") else s


def fmt_bounds(low: float, high: float) -> str:
    """Declared SESOI bounds, without rounding them to different floats."""
    return f"[{fmt_bound(low)}, {fmt_bound(high)}]"


def fmt_p(x: float, precision: int = 3) -> str:
    """Do not present a floating-point tail that became zero as an exact p=0."""
    return "underflow or unavailable (not exact zero)" if x == 0 else format(x, f".{precision}g")


def fmt_interval(lo: float, hi: float) -> str:
    """Format distinct finite endpoints without rounding both to one number.

    Add digits only when compact formatting collapses a nonzero-width interval.
    Like all displayed intervals, these endpoints are still rounded for display.
    """
    a, b = fmt(lo), fmt(hi)
    if lo < hi and float(a) >= float(b):
        for precision in range(4, 18):
            a, b = format(lo, f".{precision}g"), format(hi, f".{precision}g")
            if float(a) < float(b):
                break
    return f"[{a.replace('e+', 'e')}, {b.replace('e+', 'e')}]"


def fmt_ci(lo: float, hi: float) -> str:
    """Qualify display rounding or a width lost at machine precision."""
    interval = fmt_interval(lo, hi)
    if lo == hi:
        return (f"{interval} (endpoints rounded for display; computed endpoints coincide at machine "
                "precision, so interval width is unresolved)")
    return f"{interval} (endpoints rounded for display)"


def _fmt_percent(x: float) -> str:
    """Keep ordinary formatting without overflowing finite ratios."""
    if math.isfinite(x) and not math.isfinite(x * 100):
        return format(Decimal.from_float(x) * 100, "+.3g") + "%"
    return f"{x:+.1%}"


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
class Part:
    """One recognised part of a sentence, judged against the result."""

    rule: str      # rule id, e.g. "no-effect"
    text: str      # the exact words from the sentence; disjoint pieces joined by " … "
    status: str    # "conflict", "check" or "consistent"
    reason: str
    action: str = ""
    spans: Tuple[Tuple[int, int], ...] = ()  # character offsets in the original sentence, one per piece

    def to_dict(self) -> dict:
        return {"rule": self.rule, "text": self.text, "status": self.status, "reason": self.reason,
                "action": self.action, "spans": [list(sp) for sp in self.spans]}


_NO_PATTERN_NOTE = (
    "No supported pattern detected, so nothing was checked. statwarrant looks for English statements about "
    "no effect, equivalence, size, practical importance, direction, significance, evidence, subgroups, "
    "generalisation, certainty, causal or Bayesian wording, p-values, intervals, percentages and other numbers."
)

_UNIT_NOTE = ("Unit checking is pattern-based and partial: a limited set of simple units adjacent to a recognised "
              "effect or estimate are compared. Other units and conversions may be unchecked; verify them by hand.")


@dataclass(frozen=True)
class CheckResult:
    """Possible problems in one sentence. Never an approval of the sentence."""

    sentence: str
    parts: Tuple[Part, ...] = ()
    unchecked: Tuple[str, ...] = ()
    label: Optional[str] = None

    @property
    def warnings(self) -> Tuple[Part, ...]:
        return tuple(p for p in self.parts if p.status != CONSISTENT)

    @property
    def level(self) -> Optional[str]:
        """The most serious warning: "conflict", "check", or None."""
        ranks = [_RANK[p.status] for p in self.warnings]
        return {2: CONFLICT, 1: CHECK}[max(ranks)] if ranks else None

    @property
    def status(self) -> str:
        if self.warnings:
            return "warnings"
        return "no_warnings" if self.parts else "no_supported_pattern"

    @property
    def conflicts(self) -> Tuple[Part, ...]:
        """Parts that contradict the result."""
        return tuple(p for p in self.parts if p.status == CONFLICT)

    @property
    def to_verify(self) -> Tuple[Part, ...]:
        """Parts statwarrant recognised but could not verify; check them by hand."""
        return tuple(p for p in self.parts if p.status == CHECK)

    def __str__(self) -> str:
        conflicts, verify = self.conflicts, self.to_verify
        if self.status == "warnings":
            bits = [f"{len(conflicts)} conflict{'s' if len(conflicts) != 1 else ''}" if conflicts else "no conflicts"]
            if verify:
                bits.append(f"{len(verify)} to verify")
            tag = ", ".join(bits)
        else:
            tag = {"no_warnings": "no warnings", "no_supported_pattern": "no supported pattern detected"}[self.status]
        lines = [f"[{tag}] {self.sentence}"]
        if self.label:
            lines.append(f"  Checked against result: {self.label}")
        if not self.parts:
            lines.append("  " + _NO_PATTERN_NOTE)
            lines.append("  " + _UNIT_NOTE)
            return "\n".join(lines)
        if conflicts:
            lines.append("  Conflicts with the result:")
            for p in conflicts:
                lines.append(f"  - {p.rule:<22} \"{p.text}\": {p.reason}")
                if p.action:
                    lines.append(f"    Check: {p.action}")
        if verify:
            lines.append("  Not verified (statwarrant could not check these; review them by hand):")
            for p in verify:
                lines.append(f"  - {p.rule:<22} \"{p.text}\": {p.reason}")
        ok = [p for p in self.parts if p.status == CONSISTENT]
        if ok:
            lines.append("  Consistent with the result: " + "; ".join(f"\"{p.text}\" ({p.rule})" for p in ok) + ".")
        if self.unchecked:
            lines.append("  Not checked: " + ", ".join(f'"{u}"' for u in self.unchecked) + ".")
        lines.append("  " + _UNIT_NOTE)
        if self.status == "no_warnings":
            lines.append("  No warning is not a clearance: only the recognised parts were checked.")
        elif not conflicts:
            lines.append("  Nothing here conflicts with the result, but the parts listed were not verified; this is "
                         "not a clearance. A warning is a prompt for review, not proof that the sentence is false.")
        else:
            lines.append("  A warning is a prompt for review, not proof that the sentence is false.")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "sentence": self.sentence,
            "label": self.label,
            "status": self.status,
            "level": self.level,
            "warnings": [p.to_dict() for p in self.warnings],
            "conflicts": [p.to_dict() for p in self.conflicts],
            "to_verify": [p.to_dict() for p in self.to_verify],
            "consistent": [p.to_dict() for p in self.parts if p.status == CONSISTENT],
            "unchecked": list(self.unchecked),
            "unit_check_note": _UNIT_NOTE,
        }


@dataclass(frozen=True)
class Context:
    """Everything the judge needs besides the sentence."""

    evidence: Evidence
    units: Optional[str] = None
    scope: Optional[str] = None
    better: str = "higher"
    baseline: Optional[float] = None
    outcome: Optional[str] = None
    contrast: Optional[str] = None
    comparison_origin_is_zero: bool = True
    design: Optional[str] = None
    subgroup: Optional[str] = None

    def u(self, x: float) -> str:
        return f"{fmt(x)} {self.units}" if self.units else fmt(x)

    def bound_u(self, x: float) -> str:
        return f"{fmt_bound(x)} {self.units}" if self.units else fmt_bound(x)

    def ci_text(self, which: str = "zero") -> str:
        ev = self.evidence
        if which == "equivalence" and ev.equivalence_interval is not None:
            lo, hi = ev.equivalence_interval
            level = ev.equivalence_level
        else:
            lo, hi = ev.zero_interval
            level = ev.zero_level
        return f"{level_text(level)} CI {fmt_ci(lo, hi)}"


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #

_NOUNS = (r"(?:effects?|differences?|impacts?|associations?|relationships?|changes?|improvements?|benefits?|"
          r"gains?|increases?|decreases?|reductions?|rises?|drops?|declines?|advantages?|harms?)")
_VERBS = (r"(?:affect|change|differ|improve|increase|decrease|reduce|raise|lower|influence|help|matter|work|"
          r"benefit|boost|harm|hurt|outperform|beat|impair|worsen)")
_SMALL = r"(?:negligible|trivial|tiny|small|modest|slight|minor|minimal|marginal)"
_BIG = (r"(?:large|huge|big|dramatic(?:ally)?|massive(?:ly)?|strong(?:ly)?|considerabl[ey]|substantial(?:ly)?|"
        r"marked(?:ly)?|major|sizable|sizeable|enormous(?:ly)?|remarkabl[ey]|striking(?:ly)?|impressive(?:ly)?|"
        r"vast(?:ly)?|greatly|great|powerful(?:ly)?|profound(?:ly)?|tremendous(?:ly)?)")
_SESOI = r"(?:the\s+)?(?:smallest effect size of interest|sesoi|threshold of interest)"
_QUAL = (r"(?:about|approximately|approx\.?|around|roughly|nearly|almost|some|over|more than|less than|"
         r"at least|at most|up to|under|above|below)")
_LOWER_Q = {"over", "more than", "at least", "above"}
_UPPER_Q = {"less than", "at most", "up to", "under", "below"}
# Words that end a "compatible with ..." phrase, so negation, causal wording,
# quantifiers and new clauses are left for their own rules.
_HEDGE_STOP = (r"\b(?:no|not|never|without|none|caus\w*|due to|because|led to|leads? to|result(?:s|ed)? in|"
               r"attributable|driven|which|so|but|while|although|though|for all|for every|every|everyone|everybody|"
               r"all|each|always|generali\w*|regardless|only|safe\w*)\b|\band\b(?!\s+with\b)")
# Vocabulary the hedge rules ("compatible with", "not established", "not ruled out",
# "cannot be judged") actually assess. Any other content word in such a phrase means the
# phrase says something statwarrant did not check.
_HEDGE_VOCAB = set("""compatible with effect effects difference differences value values zero null small smaller large
larger bigger negligible trivial inside within beyond above below exceed exceeds exceeding exceeded smallest size interest
sesoi threshold bounds bound positive negative direction sign equivalence equivalent practical practically importance
important meaningful whether reaches reach reached established determined known clear shown demonstrated confirmed
ruled out cannot can't judged assessed evaluated determine judge assess evaluate without declared either true possible
inconclusive data its magnitude any these those""".split())
# A run of words inside one clause (no punctuation, no conjunction).
_CLAUSE = r"(?:(?!\b(?:but|and|while|whereas|although|though|yet|so|because|since|however)\b)[a-z' ])*"
_NEGATION = re.compile(r"\b(?:not|no|never|neither|nor|without|cannot|none|nobody|nothing|lacks?|lacked|lacking|"
                       r"failed|fails|fail)\b|n't\b")

_DIRECTION = {
    "increase": re.compile(r"\b(?:increase[sd]?|increasing|higher|raise[sd]?|rose|rise[sn]?|rising|grew|grows?|"
                           r"growing|positive(?:ly)?|greater|boost(?:s|ed)?)\b"),
    "decrease": re.compile(r"\b(?:decrease[sd]?|decreasing|lower(?:ed)?|fewer|reduce[sd]?|reducing|reductions?|"
                           r"dropped|drops?|fell|falls?|fall|declined?|declines|declining|negative(?:ly)?)\b"),
    "better": re.compile(r"\b(?:improve[sd]?|improvements?|improving|better|outperform(?:s|ed|ing)?|superior|beats?|"
                         r"gains?|help(?:s|ed)?|benefit(?:s|ed)?|enhance[sd]?|effective|works|worked)\b"),
    "worse": re.compile(r"\b(?:worse|worsen(?:s|ed|ing)?|harm(?:s|ed|ful)?|inferior|underperform(?:s|ed|ing)?|"
                        r"hurts?|impair(?:s|ed)?|deteriorat(?:e|es|ed|ion))\b"),
}

_ESTABLISHED = (r"(?:established|shown|demonstrated|found|supported|confirmed|detected|determined|observed|"
                r"reached|achieved)")
# "Neither X nor Y was established", "the data support neither X nor Y", "neither a significant
# difference nor equivalence": a statement that two things are NOT established, judged item by
# item (not a claim of no effect). Each item is a short phrase that stops at a clause boundary
# or conjunction, so claims after it ("... and prove the treatment caused harm") are still read.
_NEITHER_TOKEN = r"(?:[^\s.;,:()]|\.(?=\d))+"
_NEITHER_STOP = (r"(?:and|but|or|so|yet|while|whereas|although|because|since|which|that|thus|hence|therefore|"
                 r"nor|neither|was|were|is|are|has|have|had|could|can|prove\w*|show\w*|caus\w*)")
_NEITHER_ITEM = r"(?:\s+(?!" + _NEITHER_STOP + r"\b)" + _NEITHER_TOKEN + r"){1,8}?"
_NEITHER_END = r"(?=\s*(?:[;,:()]|\.(?!\d)|$)|\s+" + _NEITHER_STOP + r"\b)"
_NEITHER_ESTABLISHED = (
    r"\bneither" + _NEITHER_ITEM + r"\s+nor" + _NEITHER_ITEM +
    r"\s+(?:was|were|is|are|has been|have been|had been|could be|can be)\s+(?:yet\s+)?(?:statistically\s+)?"
    + _ESTABLISHED + r"\b|"
    r"\b(?:supports?|supported|shows?|showed|establish(?:es|ed)?|demonstrat(?:es|ed)|indicat(?:es|ed)|"
    r"suggest(?:s|ed)|reveal(?:s|ed)|finds?|found|provides? (?:evidence|support) for)\s+neither" + _NEITHER_ITEM +
    r"\s+nor" + _NEITHER_ITEM + _NEITHER_END + r"|"
    r"\bneither\s+(?:(?:a|an|the|any)\s+)?(?:statistically\s+)?significan\w*(?:\s+(?!" + _NEITHER_STOP + r"\b)"
    + _NEITHER_TOKEN + r"){0,6}?\s+nor" + _NEITHER_ITEM + _NEITHER_END)
# Words an item may contain and still clearly refer to the tested result.
_NEITHER_VOCAB = set("""a an the any statistically significant significantly reliable clear real true difference
differences different effect effects from zero nonzero non-zero equivalence equivalent increase decrease positive
negative improvement benefit harm association relationship change impact smallest size of interest sesoi
practically practical important meaningful relevant larger greater bigger than beyond exceeding above between
groups conditions arms two in on for across among with""".split())
_NEITHER_ESTABLISHED_RE = re.compile(_NEITHER_ESTABLISHED)
# "doubled", "halved", "three times": a claim about a ratio
_RATIO_WORDS = {"doubl": 2.0, "twice": 2.0, "two-fold": 2.0, "twofold": 2.0, "two times": 2.0, "tripl": 3.0,
                "thrice": 3.0, "three-fold": 3.0, "threefold": 3.0, "three times": 3.0, "quadrupl": 4.0,
                "four-fold": 4.0, "fourfold": 4.0, "four times": 4.0, "five-fold": 5.0, "fivefold": 5.0,
                "five times": 5.0, "ten-fold": 10.0, "tenfold": 10.0, "ten times": 10.0, "halv": 0.5,
                "half": 0.5}
# A ratio word is read as a claim about this result only when its clause names a ratio
# quantity ("doubled the odds", "the risk was halved").
_RATIO_OBJECT = re.compile(r"\b(?:odds|risks?|hazards?|rates?|likelihood|chances?|probabilit(?:y|ies)|incidence)\b")

_WORD_PATTERNS = [
    ("_skip", r"\bfalse (?:positives?|negatives?)\b|\bscope:"),
    # naming a procedure is not a claim about its outcome
    ("_skip", r"\b(?:equivalence|minim(?:al|um)[- ]effects?) (?:and|or) (?:equivalence|minim(?:al|um)[- ]effects?) "
              r"(?:tests?|testing|analys[ie]s)\b"),
    ("_skip", r"\b(?:equivalence|minimal[- ]effects?|non-?inferiority) (?:tests?|testing|analys[ie]s|procedures?|"
              r"bounds?|margins?|regions?)\b|\btost\b"),
    ("ratio", r"\b(?:doubl(?:e|ed|es|ing)|tripl(?:e|ed|es|ing)|quadrupl(?:e|ed|es|ing)|halv(?:e|ed|es|ing)|"
              r"(?:twice|thrice|(?:two|three|four|five|ten) times)(?=\s+(?:as|the|that|higher|larger|greater|more|"
              r"lower|smaller|less|fewer)\b)|(?:two|three|four|five|ten)[- ]?fold|(?:by|in) half|half (?:as|the))\b"),
    ("probability_misreading", r"\b(?:probability|chance|likelihood)\s+(?:that|of)\s+(?:the\s+)?(?:true\s+)?"
                               r"(?:effect|difference|mean|value|parameter|null|hypothesis|results?|findings?|"
                               r"estimate|population)\b|\b(?:due to|by|because of|from)\s+(?:random\s+)?chance\b"),
    ("bayesian_wording", r"\b(?:credible intervals?|posterior(?:\s+(?:probability|distribution|mean|median))?|"
                         r"bayes factors?|bayesian|prior distributions?)\b"),
    ("subgroup", r"\bonly\s+(?:for|among|in|with|within)\b|\b(?:for|among|in|within)\s+(?:the\s+)?(?:boys|girls|"
                 r"men|women|males|females|control group|treatment group|comparison group|intervention group|"
                 r"subgroups?|a subgroup|some\s+\w+|those\s+who|participants\s+who|students\s+who|"
                 r"patients\s+who|people\s+who)\b|\bsubgroups?\b|\bsubsets?\b"),
    ("compatible", r"\bcompatible with\b(?:(?!" + _HEDGE_STOP + r")[^.;])*"),
    ("not_established", r"(?:\bwhether\b[^.;]*?|\b" + _CLAUSE + r")\b(?:is|are|was|were|remains?|has|have|had)\s+"
                        r"not\s+(?:yet\s+|been\s+)*(?:established|determined|known|clear|shown|demonstrated|confirmed)\b"
                        r"(?:\s+by\s+(?:these|the)\s+data)?"),
    ("not_ruled_out", r"\b" + _CLAUSE + r"(?:\b(?:is|are|was|were|has|have|had)\s+not|\bcannot|\bcan't|\bcan not|"
                      r"\bcould not|\bcouldn't)\s+(?:be\s+|been\s+)*ruled\s+out\b"),
    ("cannot_judge", r"\b" + _CLAUSE + r"(?:\bcannot|\bcan't|\bcan not|\bis not possible to)\s+(?:be\s+)?"
                     r"(?:judged|assessed|determined|evaluated|judge|assess|determine|evaluate)\b[^.;]*"),
    ("inconclusive", r"\binconclusive\b"),
    ("evidence_absent", r"\b(?:no|little|insufficient|not enough|scant) (?:clear |strong |convincing |statistical |"
                        r"significant )?evidence (?:of|for|that)\b"),
    ("evidence", r"\b(?:strong|clear|robust|compelling|convincing|conclusive|solid|good|weak|limited|some|modest|"
                 r"suggestive|moderate|tentative|preliminary)\s+(?:statistical\s+)?evidence\b|"
                 r"\b(?:statistical\s+)?evidence\s+(?:of|for|that)\b"),
    ("marginal", r"\b(?:marginally|borderline|nearly|almost) (?:statistically )?significant\b|"
                 r"\b(?:approach(?:ed|es|ing)?|trend(?:ed|ing)? toward(?:s)?) (?:statistical )?significance\b"),
    ("nonsignificance", r"\b(?:(?:did|does|do|was|were|is|are)\s*(?:not|n't)\s+[a-z]+\s+(?:statistically\s+)?"
                        r"significantly|not (?:statistically )?significant(?:ly)?|no (?:statistically )?significant|"
                        r"non-?significant(?:ly)?|insignificant|did not reach (?:statistical )?significance|"
                        r"failed to reach (?:statistical )?significance)\b"),
    ("equivalence", r"\b(?:equivalently|equivalent|equivalence|comparable|on par|as (?:good|effective|accurate) as|"
                    r"practically (?:the same|identical|indistinguishable)|indistinguishable|interchangeable|"
                    r"no (?:meaningful|practical|practically important|important|relevant|practically relevant|"
                    r"substantial|notable|appreciable|clinically relevant|clinically meaningful) " + _NOUNS + r"|"
                    r"(?:similar|the same) (?:performance|results|outcomes|effects?|accuracy|scores)|"
                    r"perform(?:s|ed)? (?:similarly|the same|equally))\b"),
    ("small", r"\b(?:negligibl[ey]|trivial(?:ly)?)\b|"
              r"\b" + _SMALL + r"(?:,?\s+(?:but|and|yet)?\s*(?!(?:the|a|an|this|that|these|those|its|their|our|his|"
              r"her|was|were|is|are)\b)[a-z-]+){0,2}?\s+" + _NOUNS + r"\b|"
              r"\b" + _NOUNS + r"(?:\s+(?:between|in|of|for|on|across|among|from)(?:\s+[a-z0-9'-]+){1,5}?)?\s+"
              r"(?:is|was|were|are|remained|remains|seems?|seemed|appears?|appeared)\s+"
              r"(?:very |quite |rather |relatively |fairly |extremely |really )?" + _SMALL + r"\b|"
              r"\bslight(?:ly)?\b|"
              r"\b(?:smaller|less) than " + _SESOI),
    ("no_effect", r"\bno\s+(?:\w+\s+)?" + _NOUNS + r"\b|"
                  r"\b(?:did|does|do|was|were|is|are|had|has|have|could|would|will)\s*(?:not|n't)\s+(?:\w+\s+)?"
                  + _VERBS + r"\w*|"
                  r"\bnot\s+(?:any\s+)?(?:different|higher|lower|better|worse|greater|larger|smaller|superior|"
                  r"inferior|more effective|less effective)\b|"
                  r"\bno\s+(?:different|higher|lower|better|worse)\b|"
                  r"\b(?:failed|fails|fail) to\s+" + _VERBS + r"\w*|"
                  r"\b(?:ineffective|unaffected|unchanged|unrelated to|uncorrelated with)\b|"
                  r"\b(?:was|were|is|are|been|be)\s*(?:not|n't)\s+(?:associated|related|linked|correlated)\s+"
                  r"(?:with|to)\b|"
                  r"\bneither\b[^.;]*?\bnor\b(?:\s+\w+)?"),
    ("certainty", r"\b(?:prove[sdn]?|proof|conclusively|definitely|certainly|undeniabl[ey]|exactly|precisely)\b"),
    ("generalization", r"\b(?:in general|generally|always|universally|for everyone|for everybody|everyone|everybody|"
                       r"nobody|no one|none of the \w+|"
                       r"for all\b|all (?:of )?(?:the )?(?:students|users|patients|people|participants|learners|"
                       r"children|adults|models|tasks|datasets|settings|schools|classes|groups|populations|contexts|"
                       r"languages|domains|cases|individuals|subjects|respondents|conditions)|every\s+\w+|"
                       r"each\s+(?:student|user|patient|person|participant|learner|child|individual|subject|"
                       r"respondent|case|school|class|model|task|dataset|setting)|"
                       r"generali[sz](?:e|es|ed|able|ation)|in every|across (?:all|the board)|regardless of|"
                       r"any (?:student|user|patient|person|participant|setting|context|population))\b"),
    ("causal", r"\b(?:caus(?:e|es|ed|ing|al|ally)|led to|leads to|lead to|due to|because of|result(?:s|ed)? in|"
               r"attributable to|driven by|responsible for)\b"),
    ("nonzero", r"\b(?:differs?|differed|different) from zero\b|\bnon-?zero\b|\bdetectable\b"),
    ("importance", r"\b(?:meaningful(?:ly)?|important|practically (?:significant|relevant|important)|"
                   r"clinically (?:significant|relevant|meaningful|important)|"
                   r"educationally (?:significant|relevant|meaningful)|worthwhile|noteworthy|notable|"
                   r"appreciabl[ey]|matters?)\b|"
                   r"\b(?:larger|greater|bigger|more)\s+(?:in magnitude\s+)?than\s+" + _SESOI + r"|"
                   r"\b(?:exceeds?|exceeded|exceeding|beyond|above|surpass(?:es|ed)?|reach(?:es|ed)?)\s+" + _SESOI),
    ("big", r"\b" + _BIG + r"\b"),
    ("significance", r"\b(?:statistically |highly |very )?significant(?:ly)?\b|\breached significance\b"),
    ("vague_result", r"\b(?:positive|negative|null) (?:results?|findings?|outcomes?|stud(?:y|ies)|trials?)\b"),
] + [(name, pat.pattern) for name, pat in _DIRECTION.items()]

_COMPILED = [(name, re.compile(p)) for name, p in _WORD_PATTERNS]

_NUM = r"-?\d*\.?\d+(?:e[+-]?\d+)?"
# Exact aliases only: no conversion, dimensional algebra, or inference from free text.
# In particular, one-letter abbreviations such as "m" are too ambiguous here.
_SIMPLE_UNIT_GROUPS = {
    "hour": ("hour", "hours", "hr", "hrs"),
    "minute": ("minute", "minutes", "min", "mins"),
    "second": ("second", "seconds", "sec", "secs"),
    "day": ("day", "days"),
    "week": ("week", "weeks", "wk", "wks"),
    "year": ("year", "years", "yr", "yrs"),
    "meter": ("meter", "meters", "metre", "metres"),
    "centimeter": ("centimeter", "centimeters", "centimetre", "centimetres", "cm"),
    "millimeter": ("millimeter", "millimeters", "millimetre", "millimetres", "mm"),
    "kilometer": ("kilometer", "kilometers", "kilometre", "kilometres", "km"),
    "gram": ("gram", "grams"),
    "kilogram": ("kilogram", "kilograms", "kg"),
    "milligram": ("milligram", "milligrams", "mg"),
    "pound": ("pound", "pounds", "lb", "lbs"),
    "point": ("point", "points"),
}
_SIMPLE_UNITS = {alias: name for name, aliases in _SIMPLE_UNIT_GROUPS.items() for alias in aliases}
# These tokens can denote a unit but also mean other things. Detect them only to
# request review, never to infer which unit was meant.
_AMBIGUOUS_UNITS = {"h", "m", "s", "g"}
_UNIT_AFTER_NUMBER = re.compile(r"[\s-]*(" + "|".join(sorted(set(_SIMPLE_UNITS) | _AMBIGUOUS_UNITS,
                                                            key=len, reverse=True)) + r")\b")
_NEITHER_EQUIVALENCE = re.compile(
    r"\bneither\s+(?:practical\s+)?equivalence"
    r"(?:\s+within\s+(?:plus\s+or\s+minus|±|\+/-|\+-)\s*" + _NUM + r"(?:\s+[a-z][a-z-]*){0,2})?"
    r"\s+nor\s+(?:an?\s+)?effects?\b"
    r"(?:\s+(?:larger|greater|bigger|exceeding|beyond|above|more)\b[^.;,]*)?"
)
_NUMBER_PATTERNS = [
    # "95% probability", "95% confident": a probability statement, not a percentage change
    ("_skip", re.compile(r"(?<![a-z_])" + _NUM + r"\s*%(?=\s*(?:probability|chance|likelihood|confident|confidence|"
                         r"certain|sure)\b)")),
    ("plausible_value", re.compile(r"\b(?:could|may|might|can)\s+(?:be|reach|have been)\s+as\s+"
                                   r"(large|big|high|great|much|small|low|little)\s+as\s+(" + _NUM + r")")),
    ("fold", re.compile(r"(?<![a-z_])(" + _NUM + r")\s*(?:-\s*|\s+)?(?:fold\b|times(?=\s+(?:as|the|higher|larger|"
                        r"greater|more|lower|smaller|less|fewer)\b))")),
    ("interval_level", re.compile(r"(" + _NUM + r")\s*%\s*(?:confidence |credible |compatibility )?"
                                  r"(?:intervals?|ci)\b")),
    ("alpha_level", re.compile(r"(?:\b(?:alpha|α)\s*(?:=|of)\s*(" + _NUM + r"))|(?:(" + _NUM + r")\s*%\s*"
                               r"(?:significance\s+)?level\b)|(?:\bat\s+(?:the\s+)?(" + _NUM + r")\s+"
                               r"(?:significance\s+)?level\b)")),
    ("p_value", re.compile(r"\bp(?:\s*-?\s*values?)?\s*(<=|>=|=|<|>|\bof\b|\bwas\b|\bis\b|:)\s*(" + _NUM + r")")),
    ("percentage", re.compile(r"(" + _NUM + r")\s*(?:%|percent\b|per cent\b)")),
    # an ordered pair: "[1.0, 7.4]", "(1.0 to 7.4)", "from 1.0 to 7.4", "between 1.0 and 7.4", "of 1.0 to 7.4"
    ("range", re.compile(r"[\[(]\s*(" + _NUM + r")\s*(?:[a-z]+\s*)?(?:,|;|to|-)\s*(" + _NUM + r")\s*(?:[a-z]+\s*)?[\])]|"
                         r"\b(?:from|between|of|ranged from|ranging from)\s+(" + _NUM + r")\s*(?:[a-z]+\s+)?"
                         r"(?:to|and)\s+(" + _NUM + r")|"
                         r"\b(?:was|is|were)\s+(" + _NUM + r")\s*(?:[a-z]+\s+)?to\s+(" + _NUM + r")")),
    ("magnitude", re.compile(r"\bby\s+(?:(" + _QUAL + r")\s+)?(" + _NUM + r")")),
]
_CHANGE_WORDS = (r"(?:improvements?|gains?|increases?|decreases?|drops?|rises?|reductions?|differences?|effects?|"
                 r"changes?|higher|lower|better|worse|more|fewer|greater|larger|smaller|boost|benefit|advantage|"
                 r"lead|loss)")

_ROLE_PAIR = [
    ("interval", re.compile(r"\b(?:ci|cis|confidence|confident|compatibility interval|intervals?)\b")),
    ("bounds", re.compile(r"\b(?:within|bounds?|margins?|equivalence region|sesoi)\b")),
    ("compatible", re.compile(r"\b(?:compatible|plausible|consistent with)\b")),
]
_ROLE_NUMBER = [
    ("estimate", re.compile(r"\b(?:effect|estimate|estimated effect|difference|mean difference|change|improvement|gain|"
                            r"advantage|lead|benefit|"
                            r"increase|decrease|effect size)\s+(?:size\s+)?(?:was|is|of|were|equals?|=|:)\s*"
                            r"(?:about|approximately|around|roughly|~)?$")),
    ("standard error", re.compile(r"\b(?:se|s\.e\.|standard error)\s*(?:was|is|of|=|:)?$")),
    ("degrees of freedom", re.compile(r"\b(?:df|degrees of freedom)\s*(?:was|is|of|=|:)?$|\bt\s*\($")),
    ("smallest effect size of interest", re.compile(r"(?:(?:within|bounds? of|margin of)\s*(?:±|\+/-|\+-|plus or minus)\s*$)|"
                                                    r"(?:smallest effect size of interest|sesoi|threshold)\s*"
                                                    r"(?:of|was|is|=|:)?\s*\(?$")),
    ("baseline", re.compile(r"\b(?:baseline|control mean|reference level)\s*(?:of|was|is|=|:)?$")),
]


_TEST_NAMES = {
    "equivalence": re.compile(r"\bequivalence (?:tests?|testing|analys[ie]s)\b|\btost\b|\btests? (?:of|for) equivalence\b|"
                              r"\btwo one-sided tests?\b"),
    "minimal-effect": re.compile(r"\bminim(?:al|um)[- ]effects? (?:tests?|testing|analys[ie]s)\b|\bmet\b|"
                                 r"\btests? (?:of|for) (?:a )?minim(?:al|um) effects?\b"),
}
_BOTH_TESTS = re.compile(r"\b(?:equivalence|minim(?:al|um)[- ]effects?) (?:and|or) (?:equivalence|minim(?:al|um)[- ]effects?) "
                         r"(?:tests?|testing|analys[ie]s)\b")
_SEGMENT_BREAK = re.compile(r"[,;()\[\]]|\.(?!\d)")
_CLAUSE_BREAK = re.compile(r";|\.(?!\d)|\b(?:but|whereas|while|although|however)\b")
# Segments for scoping a negation: commas, semicolons, sentence ends and conjunctions.
_SEGMENT = re.compile(r"[,;]|\.(?!\d)|\b(?:and|but|while|whereas|although|so|yet|however)\b")


def _bounded(text: str, start: int, end: int, breaks) -> str:
    left = max((m.end() for m in breaks.finditer(text, 0, start)), default=0)
    m = breaks.search(text, end)
    return text[left:m.start() if m else len(text)]


def _named_test(original: str, start: int, end: int) -> Tuple[Optional[str], bool]:
    """The test a p-value or significance word refers to, from the words around it.

    Returns (name, named_elsewhere): name is "equivalence", "minimal-effect",
    "ambiguous" or None (the zero test); named_elsewhere says that another part of the
    clause names a test, so a mismatch may be a binding problem rather than an error.
    """
    seg = _bounded(original, start, end, _SEGMENT_BREAK)
    if _BOTH_TESTS.search(seg):
        return "ambiguous", False
    found = [n for n, pat in _TEST_NAMES.items() if pat.search(seg)]
    if not found:
        # "The equivalence test was not significant (p = 0.77)": a parenthesis belongs to
        # the words just before it, back to the previous comma or semicolon.
        left = max((m.end() for m in _SEGMENT_BREAK.finditer(original, 0, start)), default=0)
        if left > 0 and original[left - 1] == "(":
            lead_start = max((m.end() for m in re.finditer(r"[,;]|\.(?!\d)|\b(?:but|and|while|whereas)\b",
                                                           original[:left - 1])), default=0)
            lead = original[lead_start:left - 1]
            found = [n for n, pat in _TEST_NAMES.items() if pat.search(lead)]
    if len(found) > 1:
        return "ambiguous", False
    if found:
        return found[0], False
    clause = _bounded(original, start, end, _CLAUSE_BREAK)
    return None, any(pat.search(clause) for pat in _TEST_NAMES.values())


def _pair_role(context: str, phrase: str) -> str:
    best, pos = "unknown", -1
    for role, pat in _ROLE_PAIR:
        for m in pat.finditer(context):
            if m.start() > pos:
                best, pos = role, m.start()
    if best == "unknown" and re.match(r"(?:from|between)\b", phrase):
        return "from_to"
    return best


def _number_role(context: str) -> Optional[str]:
    tail = context.rstrip()
    for role, pat in _ROLE_NUMBER:
        if pat.search(tail):
            return role
    return None


def _coefficient_role(prefix: str, suffix: str) -> Optional[str]:
    """Recognize only an unqualified generic coefficient, not a named term."""
    # The selected term's identity is unavailable to the linter. A clause-initial
    # generic subject prevents another coefficient from silently matching it.
    if re.search(r"(?:^|[,;:(])\s*(?:the\s+)?(?:estimated\s+)?coefficient\s+"
                 r"(?:was|is|were|equals?|=|:)\s*(?:(?:about|approximately|around|roughly|~)\s*)?$", prefix):
        # A term name may follow the value, optionally after units or a comma.
        qualified = re.match(r"\s*(?:[,()]\s*)?(?:(?!(?:and|but|while|whereas|yet)\b)"
                             r"[a-z][a-z-]*\s+){0,4}(?:for|of|on|in|with|associated\s+with|corresponding\s+to)\b", suffix)
        parenthesized_name = re.match(r"\s*\(\s*[a-z]", suffix)
        if not qualified and not parenthesized_name:
            return "coefficient"
    return None


_TRANS = {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2212": "-", "\u2013": "-",
          "\u2014": " - ", "\u2264": "<=", "\u2265": ">=", "\u00a0": " "}


def _normalize(sentence: str) -> Tuple[str, List[int]]:
    """Lower-cased, padded text and, for each of its characters, the index in ``sentence`` (-1 for padding)."""
    chars, idx = [" "], [-1]
    for i, ch in enumerate(sentence):
        for c in _TRANS.get(ch, ch).lower():
            chars.append(c)
            idx.append(i)
    chars.append(" ")
    idx.append(-1)
    text = "".join(chars)
    for m in reversed(list(re.finditer(r"(?<=\d),(?=\d{3}\b)", text))):  # 1,200 -> 1200
        del chars[m.start()]
        del idx[m.start()]
    return "".join(chars), idx


def _span(sentence: str, idx: List[int], start: int, end: int) -> Tuple[str, int, int]:
    pos = [idx[k] for k in range(start, end) if 0 <= k < len(idx) and idx[k] >= 0]
    if not pos:
        return "", -1, -1
    a, b = min(pos), max(pos) + 1
    while a < b and sentence[a].isspace():
        a += 1
    while b > a and sentence[b - 1].isspace():
        b -= 1
    return sentence[a:b], a, b


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _sign_of(phrase: str, better: str) -> Optional[int]:
    """+1 / -1 for the direction words in a phrase, 0 if mixed, None if none."""
    good = 1 if better == "higher" else -1
    signs = set()
    if _DIRECTION["increase"].search(phrase):
        signs.add(1)
    if _DIRECTION["decrease"].search(phrase):
        signs.add(-1)
    if _DIRECTION["better"].search(phrase):
        signs.add(good)
    if _DIRECTION["worse"].search(phrase):
        signs.add(-good)
    if not signs:
        return None
    return signs.pop() if len(signs) == 1 else 0


def _close(x: float, s: str, q: float) -> bool:
    """Does the written number ``s`` (value ``x``) equal ``q`` up to its own rounding?"""
    body = s.lstrip("-")
    if "e" in body:
        return abs(x - q) <= 0.05 * abs(q) + 1e-300
    d = len(body.split(".")[1]) if "." in body else 0
    return abs(x - q) <= max(0.5 * 10 ** (-d), 0.005 * abs(q)) + 1e-12


def _known(ctx: Context) -> List[Tuple[str, float]]:
    ev = ctx.evidence
    k: List[Tuple[str, float]] = [("estimate", ev.estimate), ("standard error", ev.se)]
    if ev.df is not None and math.isfinite(ev.df):
        k.append(("degrees of freedom", ev.df))
    lo, hi = ev.zero_interval
    k += [(f"lower end of the {level_text(ev.zero_level)} interval", lo), (f"upper end of the {level_text(ev.zero_level)} interval", hi)]
    k.append(("interval level", ev.zero_level * 100))
    k.append(("p-value of the zero test", ev.p_zero))
    k.append(("alpha", ev.alpha))
    if ev.sesoi is not None:
        k += [("smallest effect size of interest", ev.sesoi[0]), ("smallest effect size of interest", ev.sesoi[1])]
        if ev.equivalence_level != ev.zero_level:
            elo, ehi = ev.equivalence_interval
            k += [(f"lower end of the {level_text(ev.equivalence_level)} interval", elo),
                  (f"upper end of the {level_text(ev.equivalence_level)} interval", ehi),
                  ("interval level", ev.equivalence_level * 100)]
        k += [("p-value of the equivalence test", ev.p_equivalence),
              ("p-value of the minimal-effect test", ev.p_minimal_effect)]
    if ctx.baseline is not None:
        b = ctx.baseline
        k += [("baseline", b), ("baseline plus the estimate", b + ev.estimate),
              ("baseline plus the lower end of the interval", b + lo),
              ("baseline plus the upper end of the interval", b + hi)]
    return k


def _match_known(x: float, s: str, known: List[Tuple[str, float]]) -> Optional[str]:
    """Name of a quantity in the result equal to ``x``, sign included."""
    for name, q in known:
        if q is not None and (x >= 0) == (q >= 0) and _close(abs(x), s.lstrip("-"), abs(q)):
            return name
    return None


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #

@dataclass
class _Hit:
    category: str
    phrase: str      # normalised (lower-case) words, used by the judges
    start: int       # offsets in the normalised text
    end: int
    data: Dict = field(default_factory=dict)


def _number_hit_role(h: _Hit, original: str, ctx: Context) -> Optional[str]:
    """Resolve a number's local role without treating an outcome name as an effect."""
    context = h.data.get("context", "")
    role = _number_role(context)
    if role == "estimate" and ctx.outcome:
        match = _ROLE_NUMBER[0][1].search(context.rstrip())
        outcome = _normalize(ctx.outcome)[0].strip()
        if match and outcome:
            role_start = h.start - len(context) + match.start()
            if any(m.start() <= role_start < m.end() for m in re.finditer(re.escape(outcome), original)):
                return None
    if role is None and re.search(r"\bcoefficient\b", context):
        return _coefficient_role(original[:h.start], original[h.end:])
    return role


_STOP = set("""a an the and or but so of in on at to for with by from as is are was were be been being this that
these those it its their there here than then which who whom whose what when where while also very more most much
such into over under between about after before during per both either each other same we our us they them he she
his her has have had do does did will would can could may might should shall must not no been yet thus hence
therefore however overall average on-average effect effects result results data difference differences estimate
estimated interval intervals ci finding findings analysis study observed found find show shows showed shown
suggest suggests suggested indicate indicates indicated scope""".split())


def _scan(sentence: str, ctx: Context):
    """Recognise parts of the sentence. Returns hits, residual text, coverage mask and index map."""
    text, idx = _normalize(sentence)
    original = text
    covered = [False] * len(text)

    def blank(a: int, b: int) -> None:
        nonlocal text
        text = _blank(text, a, b)
        for k in range(a, b):
            covered[k] = True

    if ctx.scope:
        # Only the "Scope: ..." note that build_claims appends; the scope words elsewhere
        # in a sentence are still read, so "all students" is caught when the scope is "students".
        scope = _normalize(ctx.scope)[0].strip()
        for m in list(re.finditer(r"\bscope:\s*" + re.escape(scope), text)):
            blank(m.start(), m.end())

    hits: List[_Hit] = []
    outcome_spans = []
    if ctx.outcome:
        phrase = _normalize(ctx.outcome)[0].strip()
        outcome_spans = [m.span() for m in re.finditer(re.escape(phrase), original)] if phrase else []

    # Numbers first, so "95% CI" is not read as a percentage change.
    for name, pat in _NUMBER_PATTERNS:
        for m in list(pat.finditer(text)):
            if name == "percentage" and _DESCRIPTIVE_SHARE.search(original[:m.start()]):
                continue  # "421 patients (27.0%)": a group's share, not an effect; left unchecked
            if name != "_skip":
                # context: the words before the match and inside it, up to its first number
                first = min((m.start(i) for i in range(1, (m.lastindex or 0) + 1) if m.group(i) is not None),
                            default=m.start())
                context = original[max(0, m.start() - 60):first]
                named, elsewhere = _named_test(original, m.start(), m.end())
                hits.append(_Hit(name, m.group(0).strip(), m.start(), m.end(),
                                 {"groups": list(m.groups()), "context": context, "named": named,
                                  "named_elsewhere": elsewhere,
                                  "clause": _bounded(original, m.start(), m.end(), _SEGMENT)}))
            blank(m.start(), m.end())
    if ctx.units:
        unit = re.escape(ctx.units.lower().strip().rstrip("s"))
        unit_pat = re.compile(r"(?:\b(" + _QUAL + r")\s+)?(" + _NUM + r")[\s-]*" + unit + r"s?\b(?=\s*(?:\w+\s+)?"
                              + _CHANGE_WORDS + r"\b)")
        for m in list(unit_pat.finditer(text)):
            hits.append(_Hit("magnitude", m.group(0).strip(), m.start(), m.end(),
                             {"groups": list(m.groups()), "units": True}))
            blank(m.start(), m.end())
    for m in list(re.finditer(r"(?<![a-z_])" + _NUM, text)):
        if _descriptive_count(original, m.start(), m.end(), ctx) or (
                _DESCRIPTIVE_SHARE.search(original[:m.start()]) and original[m.end():m.end() + 2].strip().startswith("%")):
            continue  # "28 days", "421 patients": a time or a count, not an effect; left unchecked
        hits.append(_Hit("number", m.group(0), m.start(), m.end(),
                         {"context": original[max(0, m.start() - 60):m.start()]}))
        blank(m.start(), m.end())
    for m in list(re.finditer("%", text)):
        blank(m.start(), m.end())

    # "does not prove ...": a caution, which also uses up its negation
    for m in list(_CAUTION_SPAN.finditer(text)):
        hits.append(_Hit("caution", m.group(0).strip(), m.start(), m.end(),
                         {"orig": _span(sentence, idx, m.start(), m.end())[0]}))
        blank(m.start(), m.end())
    # Neither equivalence nor an effect is not a no-effect or positive-equivalence
    # claim. Request review instead of asserting that the clause is verified.
    for m in _NEITHER_EQUIVALENCE.finditer(original):
        hits.append(_Hit("neither_equivalence", m.group(0), m.start(), m.end()))
        blank(m.start(), m.end())
    # Other "neither X nor Y was established" statements: judged item by item (_judge_neither).
    for m in list(_NEITHER_ESTABLISHED_RE.finditer(text)):
        hits.append(_Hit("neither_established", m.group(0).strip(), m.start(), m.end(),
                         {"orig": _span(sentence, idx, m.start(), m.end())[0]}))
        blank(m.start(), m.end())

    for name, pat in _COMPILED:
        for m in list(pat.finditer(text)):
            clause = _bounded(original, m.start(), m.end(), _SEGMENT)
            if name == "ratio" and not _RATIO_OBJECT.search(clause):
                continue  # "halved dropout": a ratio about something else; left unchecked
            if name != "_skip":
                named, elsewhere = _named_test(original, m.start(), m.end())
                hits.append(_Hit(name, m.group(0).strip(), m.start(), m.end(),
                                 {"before": original[max(0, m.start() - 40):m.start()], "named": named, "clause": clause,
                                  "named_elsewhere": elsewhere, "orig": _span(sentence, idx, m.start(), m.end())[0],
                                  "in_outcome": any(a <= m.start() and m.end() <= b for a, b in outcome_spans)}))
            blank(m.start(), m.end())

    # "0.9 percentage points" about a result stored as a proportion (0.009): read the
    # sentence's outcome-scale numbers on the stored scale.
    mode = _percentage_points(original, ctx)
    if mode:
        after_pp = [m.end() - 1 for m in re.finditer(_PP + r"\s*\(", original)]  # the "(" after "points"
        for h in hits:
            if h.category not in ("magnitude", "range", "number", "plausible_value"):
                continue
            attached = bool(re.match(r"\s*(?:[a-z]+\s+)?" + _PP, original[h.end:]))
            if not attached and h.category == "range":  # "0.9 percentage points (95% CI -0.7 to 2.5)"
                attached = any(p <= h.start and ")" not in original[p + 1:h.start] for p in after_pp)
            if mode == "convert" and attached:
                _rescale(h)
                h.data["pp"] = True
            elif mode == "convert":
                h.data["pp_alt"] = True  # judged as written; see check_sentence
            elif attached:
                h.data["pp_units"] = True

    # Bind a unit only to the number immediately before it, never to a nearby CI,
    # p-value, df, or a different number in the clause. Percentage points have their
    # own pre-existing rules above and are intentionally not handled here.
    multiple_models = bool(re.search(r"\bmodels\b", original) or len(re.findall(r"\bmodel\b", original)) > 1 or
                           re.search(r"\bmodel\s+[a-z0-9_.-]+\s+(?:and|or|vs\.?)\s+[a-z0-9_.-]+\b", original))
    for h in hits:
        unit = _effect_unit(h, original, ctx)
        if unit is not None:
            name, start, end, compound = unit
            h.data.update(unit=name, unit_span=(start, end), unit_compound=compound, multiple_models=multiple_models)
            blank(start, end)
    return hits, text, covered, idx, original


_PP = r"(?:percentage[- ]points?|\bpp\b|%[- ]points?)"
_PROPORTION_UNITS = re.compile(r"\b(?:accuracy|proportion|rate|probability|share|fraction|prevalence|risk|recall|"
                               r"precision|f1|auc|sensitivity|specificity|coverage)\b")


def _percentage_points(original: str, ctx: Context) -> Optional[str]:
    """'convert' when the sentence speaks of percentage points about a result stored as a
    proportion; 'unknown_units' when it does but the declared units are not a proportion."""
    if not re.search(_PP, original):
        return None
    units = (ctx.units or "").lower()
    if re.search(r"percent|point|%", units):
        return None  # the result is already on a percentage scale
    ev = ctx.evidence
    small = max(abs(ev.estimate), abs(ev.zero_interval[0]), abs(ev.zero_interval[1])) <= 1
    return "convert" if small and _PROPORTION_UNITS.search(units) else "unknown_units"


def _rescale(h: "_Hit") -> None:
    if h.data.get("groups"):
        h.data["groups"] = [_scale_pp(g) if g is not None and re.fullmatch(_NUM, g) else g for g in h.data["groups"]]
    if h.category == "number":
        h.phrase = _scale_pp(h.phrase)


def _scale_pp(s: str) -> str:
    """A written number in percentage points, as a proportion with the same precision (0.9 -> 0.009)."""
    return format(Decimal(s).scaleb(-2), "f")


def _effect_unit(h: _Hit, original: str, ctx: Context):
    """Return an immediately adjacent, whitelisted unit for an effect/estimate hit.

    This is deliberately not a general unit parser. Unknown text and composite
    units remain unchecked; percentage-point and non-effect numeric roles keep
    their existing, separate handling.
    """
    if h.category == "number":
        role = _number_hit_role(h, original, ctx)
        if role not in ("estimate", "coefficient"):
            return None
    elif h.category != "magnitude":
        return None
    number = re.search(_NUM, original[h.start:h.end])
    if number is None:
        return None
    num_end = h.start + number.end()
    if re.match(r"\s*" + _PP, original[num_end:]):
        return None
    unit = _UNIT_AFTER_NUMBER.match(original, num_end)
    if unit is None:
        return None
    # A ratio or hyphenated compound is not a simple unit even if it begins with
    # a known token (e.g. "hours per day" or "hour-long").
    compound = bool(re.match(r"\s*(?:/|\bper\b|-[a-z])", original[unit.end():]))
    return _SIMPLE_UNITS.get(unit.group(1)), unit.start(1), unit.end(1), compound


def _unchecked(sentence: str, text: str, covered: List[bool], idx: List[int], units: Optional[str]) -> Tuple[str, ...]:
    """Runs of the sentence that no rule looked at and that contain a content word."""
    stop = set(_STOP)
    runs, k = [], 0
    while k < len(text):
        if covered[k]:
            k += 1
            continue
        j = k
        while j < len(text) and not covered[j]:
            j += 1
        words = re.findall(r"[a-z][a-z'\-]*", text[k:j])
        if any(w not in stop for w in words):
            span, _, _ = _span(sentence, idx, k, j)
            span = span.strip(" ,;:.()[]")
            if span:
                runs.append(span)
        k = j
    return tuple(runs)


# --------------------------------------------------------------------------- #
# Judging
# --------------------------------------------------------------------------- #

def _topic(phrase: str) -> List[str]:
    t = []
    if re.search(r"equivalen", phrase):
        t.append("equivalence")
    if re.search(r"smallest effect size|sesoi|threshold|importan|meaningful|practical|\breach", phrase):
        t.append("importance")
    if re.search(r"\b(?:large|larger|beyond|exceed\w*|bigger|above)\b", phrase):
        t.append("large")
    if re.search(r"\b(?:small|smaller|negligible|trivial|inside|within)\b", phrase):
        t.append("small")
    if re.search(r"\bdirection\b|\bsign\b|\bpositive\b|\bnegative\b", phrase):
        t.append("direction")
    if re.search(r"\bzero\b|\bno effect\b|\bnull\b", phrase):
        t.append("zero")
    if re.search(r"differ|effect", phrase):
        t.append("effect")
    return t


# "does not prove", "cannot imply", "whether ... causal": a caution, not a claim. ("Did not show
# a difference" is an evidence statement, judged elsewhere, so show/establish are not included.)
_CAUTION_SPAN = re.compile(r"\b(?:not|cannot|never)\s+(?:\w+\s+){0,2}?(?:prove[sdn]?|proof|imply|implies)\b|"
                           r"n't\s+(?:\w+\s+){0,2}?(?:prove|imply)\b")
_CAUTION = re.compile(_CAUTION_SPAN.pattern + r"|\bwhether\b[^.;]*\bcaus|\bcaus\w*[^.;]*\bcannot be (?:determined|established)")
_SUBGROUP_GENERIC = set("""patients patient people participants participant those who were was are is receiving received
receive taking took given with without among only either group groups subgroup subgroups adults children women men
the a an of in on for and or not no non any all some""".split())


def _subgroup_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z-]+", text.lower()) if len(w) > 2 and w not in _SUBGROUP_GENERIC}


_COUNT_NOUNS = (r"(?:patients?|participants?|subjects?|people|persons?|individuals?|women|men|children|adults|"
                r"cases?|deaths?|studies|trials?|centres?|centers?|hospitals?|sites?|items?|questions?|cups?|"
                r"records?|respondents?|households?|schools?|students?|pupils?|animals?|mice|rats|cells?|samples?)")
_TIME_NOUNS = r"(?:days?|weeks?|months?|years?|hours?)"
_DESCRIPTIVE_COUNT = re.compile(r"\s+(" + _COUNT_NOUNS + r")\b")
_TIME_POINT_BEFORE = re.compile(r"\b(?:at|within|by|after|over|during|for|up to|in|of|until|before)\s*$")
_TIME_POINT_AFTER = re.compile(r"(?:-\s*" + _TIME_NOUNS.replace("s?", "") + r"\b|\s+" + _TIME_NOUNS + r"\b)")
_DESCRIPTIVE_SHARE = re.compile(r"\b\d[\d,]*\s+(?:[a-z-]+\s+){0,2}?" + _COUNT_NOUNS + r"\s*\(\s*$")


def _descriptive_count(original: str, start: int, end: int, ctx: "Context") -> bool:
    """A count ("421 patients") or a time point ("at 28 days", "28-day mortality"), not an
    effect, unless its noun is the declared unit of the effect."""
    units = (ctx.units or "").lower()
    m = _DESCRIPTIVE_COUNT.match(original, end)
    if m:
        return not (units and m.group(1).rstrip("s") in units)
    m = _TIME_POINT_AFTER.match(original, end)
    if m and (original[end:end + 1] == "-" or _TIME_POINT_BEFORE.search(original[:start])):
        return not units or not any(t in units for t in ("day", "week", "month", "year", "hour"))
    return False


_UNBOUND_PREFIX = "Not checked against the result:"
_UNBOUND_WHAT = {
    "percentage": "this percentage", "magnitude": "this size", "range": "this interval",
    "significance": "this significance statement", "nonsignificance": "this significance statement",
    "marginal": "this significance statement", "evidence": "this evidence statement",
    "evidence_absent": "this evidence statement", "importance": "this importance claim",
    "big": "this size word", "small": "this size word", "ratio": "this ratio", "fold": "this ratio",
    "plausible_value": "this interval end",
}


def _judge_hit(h: _Hit, ctx: Context, sign: Optional[int]) -> Tuple[str, str]:
    ev = ctx.evidence
    has_sesoi = ev.sesoi is not None
    z = ctx.ci_text()
    cat = h.category

    if cat == "neither_equivalence":
        return CHECK, ("This coordinated negation does not necessarily assert equivalence or no effect. "
                       "Check both propositions and their bounds by hand; the clause has not been verified.")
    if cat == "no_effect":
        neg = _sign_of(h.phrase, ctx.better)
        if neg in (1, -1):
            if ev.direction == neg:
                return CONFLICT, f"The data show an effect in exactly that direction ({z})."
            if ev.direction == -neg:
                return CHECK, (f"Literally true, but the data show the effect goes the other way ({z}). "
                                 f"Say that directly.")
        if ev.differs_from_zero:
            return CONFLICT, f"The data show an effect different from zero ({z})."
        if ev.equivalent:
            low, high = ev.sesoi
            return CONFLICT, (f"Equivalence rules out effects outside {fmt_bounds(low, high)}, not every effect. "
                             f"Say the effect is practically equivalent within these bounds.")
        return CONFLICT, (f"A non-significant result is not evidence of no effect: the data are compatible with "
                         f"effects within the {z}.")

    named = h.data.get("named")
    if named in ("equivalence", "minimal-effect", "ambiguous") and cat in (
            "significance", "nonsignificance", "evidence_absent", "marginal"):
        return _judge_named_test(cat, named, ctx)

    if cat in ("nonsignificance", "evidence_absent"):
        if ev.differs_from_zero and sign in (1, -1) and ev.direction == -sign:
            return CHECK, (f"Literally true, but the result is significant in the opposite direction ({z}, "
                             f"p = {fmt_p(ev.p_zero)}). Say that directly.")
        if ev.differs_from_zero:
            return CONFLICT, f"The result is statistically significant ({z}, p = {fmt_p(ev.p_zero)})."
        return CHECK, (f"Literally true, but readers often take it to mean 'no effect'. Add the interval: "
                         f"the data are compatible with effects in the {z}.")

    if cat == "evidence":
        strong = re.match(r"(?:strong|clear|robust|compelling|convincing|conclusive|solid|good)\b", h.phrase)
        weak = re.match(r"(?:weak|limited|some|modest|suggestive|moderate|tentative|preliminary)\b", h.phrase)
        if weak:
            return CHECK, (f"statwarrant does not grade evidence strength. The zero test gives p = {fmt_p(ev.p_zero)} "
                             f"({z}); report that instead of a label.")
        if not ev.differs_from_zero:
            return CONFLICT, f"A difference from zero is not established ({z}, p = {fmt_p(ev.p_zero)})."
        if strong:
            return CHECK, (f"The zero test rejects (p = {fmt_p(ev.p_zero)}), but statwarrant does not grade how strong "
                             f"the evidence is. Report the p-value and interval ({z}).")
        return CONSISTENT, f"The zero test rejects ({z}, p = {fmt_p(ev.p_zero)})."

    if cat == "marginal":
        if ev.differs_from_zero:
            return CHECK, f"The result is significant ({z}, p = {fmt_p(ev.p_zero)}); 'marginal' understates it."
        return CONFLICT, (f"The difference from zero is not significant (p = {fmt_p(ev.p_zero)}). 'Marginally significant' "
                         f"invites reading it as an effect; report the interval ({z}).")

    if cat == "equivalence":
        if not has_sesoi:
            return CONFLICT, "No smallest effect size of interest was declared, so equivalence cannot be assessed."
        low, high = ev.sesoi
        if ev.equivalent:
            return CONSISTENT, f"The equivalence test rejects effects outside {fmt_bounds(low, high)} ({ctx.ci_text('equivalence')})."
        return CONFLICT, (f"Equivalence within {fmt_bounds(low, high)} is not established by the equivalence test "
                          f"({ctx.ci_text('equivalence')}).")

    if cat == "small":
        if not has_sesoi:
            return CONFLICT, "No smallest effect size of interest was declared, so 'small' or 'negligible' cannot be assessed."
        low, high = ev.sesoi
        if ev.exceeds_sesoi:
            return CONFLICT, f"The effect exceeds the smallest effect size of interest ({z})."
        if ev.equivalent:
            return CONSISTENT, f"The equivalence test establishes an effect within {fmt_bounds(low, high)} ({ctx.ci_text('equivalence')})."
        return CONFLICT, (f"Equivalence within the smallest effect size of interest {fmt_bounds(low, high)} "
                          f"is not established ({ctx.ci_text('equivalence')}), so a small effect is not established.")

    if cat == "big":
        if sign in (1, -1) and ev.direction in (1, -1) and sign != ev.direction:
            return CONFLICT, f"The stated direction is opposite to the direction established by the {z}."
        return CHECK, (f"'{h.phrase}' has no defined magnitude scale here. The {z} describes the effect; "
                       "a smallest effect of interest does not define 'large', and statistical significance "
                       "alone does not establish practical importance.")
    if cat == "importance":
        if not has_sesoi:
            return CONFLICT, ("No smallest effect size of interest was declared, so practical importance or size "
                             "cannot be assessed.")
        low, high = ev.sesoi
        if not ev.exceeds_sesoi:
            return CONFLICT, (f"The minimal-effect test does not establish an effect beyond the smallest effect "
                              f"size of interest ({fmt_bounds(low, high)}; {z}).")
        if sign in (1, -1) and sign != ev.direction:
            return CONFLICT, "The effect exceeds the smallest effect size of interest, but in the opposite direction to the one stated."
        return CONSISTENT, f"The whole {z} lies beyond the smallest effect size of interest."

    if cat == "significance":
        if not ev.differs_from_zero:
            return CONFLICT, f"The difference from zero is not statistically significant ({z}, p = {fmt_p(ev.p_zero)})."
        if sign in (1, -1) and sign != ev.direction:
            return CONFLICT, "The result is significant, but in the opposite direction to the one stated."
        return CONSISTENT, f"{z} excludes zero (p = {fmt_p(ev.p_zero)})."

    if cat == "nonzero":
        if ev.differs_from_zero:
            return CONSISTENT, f"{z} excludes zero."
        return CONFLICT, f"A difference from zero is not established ({z})."

    if cat == "generalization":
        where = f"'{ctx.scope}'" if ctx.scope else "the setting that was studied (no scope was declared)"
        if re.search(r"\b(?:every|each|everyone|everybody|all|any)\b", h.phrase):
            return CONFLICT, (f"An average effect does not show that every individual or case is affected, and the "
                             f"evidence comes from {where} only.")
        return CONFLICT, f"The evidence comes from {where} only; it does not show the effect holds beyond it."

    if cat == "caution" or (cat in ("certainty", "causal") and _CAUTION.search(h.data.get("clause", "") or h.phrase)):
        return CONSISTENT, "A caution (the data do not prove or imply this), not a claim."

    if cat == "certainty":
        return CONFLICT, (f"Statistics does not prove, and the estimate is uncertain: report the interval "
                         f"({z}), not a single exact value.")

    if cat == "causal":
        if ctx.design == "observational":
            return CONFLICT, ("Causal wording, but the plan declares an observational design: the result shows an "
                              "association. (A causal design with stated assumptions would need to be described.)")
        if ctx.design == "randomised":
            if ev.differs_from_zero:
                return CONSISTENT, (f"Randomised design (as declared) and an established average effect ({z}); "
                                    f"causal wording about that average effect is supported.")
            return CHECK, (f"Randomised design (as declared), but the effect is not established ({z}); causal "
                           f"wording overstates it.")
        return CHECK, ("Whether causal wording is warranted depends on the design (randomisation, confounding), "
                       "which statwarrant does not know. Declare design='randomised' or 'observational'.")

    if cat == "subgroup":
        if ctx.subgroup:
            said = _subgroup_words(h.data.get("clause", "") or h.phrase)
            declared = _subgroup_words(ctx.subgroup)
            negated = (lambda t: bool(re.search(r"\b(?:not|no|non|without)\b|n't", t.lower())))
            if said & declared and negated(h.data.get("clause", "")) == negated(ctx.subgroup):
                return CONSISTENT, (f"The result is declared as a subgroup result ({ctx.subgroup}), and the sentence "
                                    f"names it ({', '.join(sorted(said & declared))}).")
            return CHECK, (f"The result is declared for the subgroup '{ctx.subgroup}'; the sentence may name a "
                           f"different one.")
        return CHECK, ("The result is the average difference between the compared conditions. A claim about one "
                       "group alone, or about a subgroup, needs its own analysis. If the result is itself a subgroup "
                       "result, declare subgroup='...'.")

    if cat == "bayesian_wording":
        return CHECK, ("This result comes from a frequentist analysis. Bayesian terms (credible interval, posterior, "
                       "Bayes factor) describe a different analysis with a different interpretation.")

    if cat == "probability_misreading":
        if re.search(r"chance|null|hypothesis", h.phrase):
            return CHECK, ("A p-value is not the probability that the null hypothesis is true or that the result "
                           "is due to chance.")
        return CHECK, ("A confidence interval does not give the probability that the effect lies inside it; "
                       "that needs a Bayesian analysis.")

    if cat == "vague_result":
        return CHECK, f"'{h.phrase}' is ambiguous: state the direction, the interval ({z}) and what was tested."

    if cat == "inconclusive":
        if ev.claim_class.startswith("inconclusive"):
            return CONSISTENT, f"Neither a difference from zero nor equivalence is established ({z})."
        return CONFLICT, f"The result is not inconclusive: it is classified as '{ev.claim_class.replace('_', ' ')}'."

    if cat in ("not_established", "not_ruled_out", "compatible", "cannot_judge"):
        return _judge_uncertainty(cat, h.phrase, ctx, h.data.get("orig"))

    if cat == "neither_established":
        return _judge_neither(h, ctx)

    if cat == "ratio":
        return _judge_factor(_ratio_factor(h.phrase), h.phrase, ctx, h.data.get("clause", ""))

    raise KeyError(cat)


def _ratio_factor(phrase: str) -> Optional[float]:
    norm = re.sub(r"[\s-]+", "", phrase.lower())
    for key in sorted(_RATIO_WORDS, key=len, reverse=True):
        if re.sub(r"[\s-]+", "", key) in norm:
            return _RATIO_WORDS[key]
    return None


_RATIO_QUANTITY = (("odds", r"\bodds\b"), ("hazard", r"\bhazards?\b"),
                   ("rate", r"\b(?:rates?|incidence)\b"),
                   ("risk", r"\b(?:risks?|probabilit(?:y|ies)|chances?|likelihood)\b"))


def _ratio_scale(units: str) -> Optional[str]:
    """The ratio quantity a log-scale result measures, from its declared units."""
    u = units.lower()
    if not re.search(r"\blog\b|\blog[- ]|logit|\bln\b", u):
        return None
    for name, pat in _RATIO_QUANTITY:
        if re.search(pat, u) or (name == "odds" and "logit" in u):
            return name
    return "unknown"


def _exp(x: float) -> float:
    return math.exp(x) if x < 700 else math.inf


def _judge_factor(f: Optional[float], written: str, ctx: Context, clause: str = "") -> Tuple[str, str]:
    """A ratio claim ("doubled the odds", "a 3-fold increase in the rate").

    Judged only on a log scale whose quantity (odds, risk, rate, hazard) matches the one the
    sentence names, or against the relative change when a baseline is declared. Which group
    is the numerator is not verified, so the claim is never marked consistent, and a conflict
    needs the factor to be ruled out in both orders.
    """
    ev = ctx.evidence
    lo, hi = ev.zero_interval
    level = level_text(ev.zero_level)
    clause = clause.lower()
    if f is None or not f > 0:
        return CHECK, f"'{written}' was read as a ratio, but statwarrant could not tell which factor it states."
    if re.search(r"\b(?:not|no|never|without|neither|nor)\b|n't\b", clause):
        return CHECK, f"'{written}' is negated or qualified; statwarrant does not check negated ratio claims."
    named = [name for name, pat in _RATIO_QUANTITY if re.search(pat, clause)]
    scale = _ratio_scale(ctx.units or "")
    order = "statwarrant does not verify which group is the numerator, so check the order by hand"
    if scale is not None:
        if scale == "unknown" or not named or named[0] != scale:
            what = named[0] if named else "an unnamed quantity"
            on = f"a log {scale}" if scale != "unknown" else "a log scale of unknown quantity"
            return CHECK, (f"'{written}' states a ratio of {what}, but the result is on {on} ({ctx.units}); "
                           f"odds, risk, rate and hazard ratios differ, so this was not checked.")
        lf, est_f, lo_f, hi_f = math.log(f), _exp(ev.estimate), _exp(lo), _exp(hi)
        text = (f"on the {scale}-ratio scale the estimate is a factor of {fmt(est_f)} ({level} CI {fmt(lo_f)} to "
                f"{fmt(hi_f)})")
        if not lo <= lf <= hi and not lo <= -lf <= hi:
            return CONFLICT, f"A factor of {fmt(f)} is not compatible with the data in either order: {text}."
        if abs(lf - ev.estimate) <= math.log(1.05):
            return CHECK, f"A factor of {fmt(f)} matches the estimate ({text}), but {order}."
        return CHECK, (f"A factor of {fmt(f)} is not the estimate: {text}; {order}. Report the estimate and "
                       f"interval instead of a single factor.")
    if ctx.baseline and named and named[0] in ("rate", "risk"):
        b = ctx.baseline
        rel = ev.estimate / b
        rlo, rhi = sorted((lo / b, hi / b))
        text = (f"the relative change is {rel:+.1%} of the baseline ({level} CI {rlo:+.1%} to {rhi:+.1%}), "
                f"a factor of {fmt(1 + rel)}")
        if not rlo <= f - 1 <= rhi and not rlo <= 1 / f - 1 <= rhi:
            return CONFLICT, f"A factor of {fmt(f)} is not compatible with the data in either order: {text}."
        return CHECK, f"Compare the factor {fmt(f)} with the data: {text}; {order}."
    return CHECK, (f"'{written}' states a ratio (a factor of {fmt(f)}). statwarrant checks ratios only for a "
                   f"log-scale result whose units name the same quantity (odds, risk, rate or hazard), or a rate or "
                   f"risk with a declared baseline; report the estimate and interval.")


def _neither_kind(item: str, ctx: Context) -> Optional[str]:
    if re.search(r"\d", item):
        return "threshold"  # "equivalence within ±20 points": a threshold of its own
    if re.search(r"smallest effect size|sesoi|threshold of interest|practical(?:ly)? (?:important|relevant|"
                 r"significant)|\bmeaningful|\bimportan", item):
        return "importance"
    if re.search(r"equivalen|practically (?:the same|identical)|negligib", item):
        return "equivalence"
    if _sign_of(item, ctx.better) is not None:
        return "direction"
    if re.search(r"significan|\bzero\b|differen|effect|associat|relationship|change|impact", item):
        return "zero"
    return None


def _judge_neither(h: _Hit, ctx: Context) -> Tuple[str, str]:
    """'Neither X nor Y was established': each of X and Y must indeed not be established."""
    ev = ctx.evidence
    z, e = ctx.ci_text(), ctx.ci_text("equivalence")
    text = (h.data.get("orig") or h.phrase).lower()
    m = re.search(r"\bneither\b(.*?)\bnor\b(.*)$", text, re.S)
    if not m:
        return CHECK, "statwarrant could not separate the two parts of this 'neither ... nor'."
    second = re.split(r"\b(?:was|were|is|are|has been|have been|had been|could be|can be)\s+", m.group(2))[0]
    established, checks, unknown, directions = [], [], [], []
    for item in (m.group(1), second):
        kind = _neither_kind(item, ctx)
        if kind is None:
            unknown.append(item.strip(" ,"))
            continue
        if kind == "threshold":
            checks.append(f"'{item.strip(' ,')}' names its own threshold, which was not compared with the declared "
                          f"one")
            continue
        own = set(re.findall(r"[a-z0-9'-]+", " ".join(x for x in (ctx.outcome, ctx.units, ctx.contrast) if x).lower()))
        extra = [w for w in re.findall(r"[a-z][a-z'-]*", item) if w not in _NEITHER_VOCAB and w not in own]
        if extra:
            checks.append(f"'{item.strip(' ,')}' may refer to something other than the tested result "
                          f"('{' '.join(extra)}' is not part of the declared outcome or contrast)")
            continue
        if kind in ("equivalence", "importance") and ev.sesoi is None:
            checks.append(f"no smallest effect size of interest was declared, so '{item.strip(' ,')}' was not "
                          f"tested")
            continue
        if kind == "equivalence":
            if ev.equivalent and ev.level_conflict:
                checks.append(f"equivalence is established at the {level_text(ev.equivalence_level)} level ({e}) "
                              f"but not with the {z}; say which level you mean")
            elif ev.equivalent:
                established.append(f"equivalence is established ({e})")
        elif kind == "importance":
            if ev.exceeds_sesoi:
                established.append(f"the effect exceeds the smallest effect size of interest ({z})")
        elif kind == "direction":
            directions.append(_sign_of(item, ctx.better))
        elif ev.differs_from_zero:
            established.append(f"a difference from zero is established ({z})")
    if directions and ev.direction != 0:
        # Which written direction matches the result depends on the comparison's order; only
        # "neither an increase nor a decrease" can be judged without knowing it.
        if {1, -1} <= set(directions):
            established.append(f"a direction is established ({z})")
        else:
            checks.append("a direction is established, and whether it is the one named here depends on the order "
                          "of the comparison, which statwarrant does not verify")
    if established:
        return CONFLICT, "Understates the result: " + "; ".join(established) + "."
    if checks:
        return CHECK, "Partly checked: " + "; ".join(checks) + "."
    if unknown:
        return CHECK, f"statwarrant cannot tell what '{unknown[0]}' refers to, so the statement is not fully checked."
    return CONSISTENT, f"Correct: neither is established ({z}" + (f"; {e}" if e != z else "") + ")."


def _judge_named_test(cat: str, named: str, ctx: Context) -> Tuple[str, str]:
    """'The equivalence test was (not) significant' and the like."""
    ev = ctx.evidence
    if named == "ambiguous":
        return CHECK, "This part names more than one test, so statwarrant cannot tell which result is meant."
    if ev.sesoi is None:
        return CHECK, f"No {named} test was run: no smallest effect size of interest was declared."
    if named == "equivalence":
        decided, q, thr, iv = ev.equivalent, ev.p_equivalence, ev.equivalence_threshold, ctx.ci_text("equivalence")
    else:
        decided, q, thr, iv = ev.exceeds_sesoi, ev.p_minimal_effect, ev.met_threshold, ctx.ci_text()
    says_significant = cat == "significance"
    if cat == "marginal":
        return CHECK, f"The {named} test gives p = {fmt_p(q, 4)} against a per-side threshold of {fmt(thr)} ({iv})."
    if says_significant == decided:
        return CONSISTENT, f"The {named} test gives p = {fmt_p(q, 4)} against a per-side threshold of {fmt(thr)} ({iv})."
    return CONFLICT, (f"The {named} test {'does not reject' if says_significant else 'rejects'}: p = {fmt_p(q, 4)} against "
                      f"a per-side threshold of {fmt(thr)} ({iv}).")


def _unassessed(phrase: str, ctx: Context, original_words: Optional[str] = None) -> List[str]:
    """Content words in a hedge phrase that the hedge rules do not assess.

    Names are not claims: acronyms written in capitals ("PSI", "SVM's") and words of
    the declared outcome or scope are ignored.
    """
    names = set()
    if original_words:
        names.update(w.lower() for w in re.findall(r"\b[A-Z][A-Z0-9]+(?=\b|'s)", original_words))
    for text in (ctx.outcome, ctx.scope):
        if text:
            names.update(re.findall(r"[a-z][a-z'\-]*", text.lower()))
    units = set()
    if ctx.units:
        for w in re.findall(r"[a-z][a-z'\-]*", ctx.units.lower()):
            units.update({w, w.rstrip("s"), w.rstrip("s") + "s"})
    out = []
    for w in re.findall(r"[a-z][a-z'\-]*", phrase):
        w = w[:-2] if w.endswith("'s") else w
        if w in _STOP or w in _HEDGE_VOCAB or w in units or w in names:
            continue
        if any(pat.fullmatch(w) for pat in _DIRECTION.values()):
            continue
        out.append(w)
    return out


def _judge_uncertainty(cat: str, phrase: str, ctx: Context, original_words: Optional[str] = None) -> Tuple[str, str]:
    status, reason = _judge_uncertainty_core(cat, phrase, ctx)
    extra = _unassessed(phrase, ctx, original_words)
    if status == CONSISTENT and extra:
        return CHECK, (f"{reason} But the phrase also says '{' '.join(extra)}', which statwarrant did not check, "
                       f"so the phrase as a whole is not confirmed.")
    return status, reason


def _judge_uncertainty_core(cat: str, phrase: str, ctx: Context) -> Tuple[str, str]:
    ev = ctx.evidence
    z = ctx.ci_text()
    topics = _topic(phrase)

    if cat == "cannot_judge":
        if "importance" in topics:
            if ev.sesoi is None:
                return CONSISTENT, "No smallest effect size of interest was declared."
            return CONFLICT, "A smallest effect size of interest was declared, so this can be judged."
        return CHECK, "statwarrant cannot tell which judgement is said to be impossible."

    if cat == "not_established":
        whether = phrase.startswith("whether")
        e = ctx.ci_text("equivalence")
        for t in topics:
            cite = z
            if t == "equivalence":
                ok, why, cite = not ev.equivalent, "equivalence is established", e
            elif t == "importance":
                ok = not ev.exceeds_sesoi and not (whether and ev.equivalent)
                why = "the comparison with the smallest effect size of interest is decided"
            elif t == "direction":
                sg = _sign_of(phrase, ctx.better)
                if sg in (1, -1):
                    ok, why = ev.direction != sg, "that direction is established"
                else:
                    ok, why = ev.direction == 0, "the direction is established"
            elif t in ("zero", "effect"):
                ok, why = not ev.differs_from_zero, "a difference from zero is established"
            else:
                continue
            if ok:
                return CONSISTENT, f"Correct: it is not established ({cite})."
            return CONFLICT, f"Understates the result: {why} ({cite})."
        return CHECK, "statwarrant cannot tell which claim is said to be not established."

    # "compatible with X" and "X is not ruled out" say the same thing: X is inside the interval.
    lo, hi = ev.zero_interval
    e = ctx.ci_text("equivalence")
    sg = _sign_of(phrase, ctx.better)
    failures, checks, judged = [], [], False
    if "zero" in topics:
        judged = True
        if ev.differs_from_zero:
            failures.append(f"an effect of zero is ruled out ({z})")
    if "small" in topics or ("equivalence" in topics and cat == "not_ruled_out"):
        judged = True
        if ev.exceeds_sesoi:
            failures.append(f"effects smaller than the smallest effect size of interest are ruled out ({z})")
    if "large" in topics or "importance" in topics:
        judged = True
        if ev.equivalent and ev.level_conflict:
            checks.append(f"At the {level_text(ev.equivalence_level)} level used for equivalence, effects beyond the "
                          f"smallest effect size of interest are ruled out ({e}), but the {z} still contains some. "
                          f"Say which level you mean.")
        elif ev.equivalent:
            failures.append(f"effects beyond the smallest effect size of interest are ruled out ({e})")
    if sg in (1, -1):
        judged = True
        if (sg > 0 and hi <= 0) or (sg < 0 and lo >= 0):
            failures.append(f"the {z} contains no {'positive' if sg > 0 else 'negative'} values")
    if failures:
        return CONFLICT, "Not compatible with the data: " + "; ".join(failures) + "."
    if checks:
        return CHECK, " ".join(checks)
    if judged or "effect" in topics:
        return CONSISTENT, f"Correct: the data do not rule it out ({z})."
    return CHECK, "statwarrant cannot tell what is said to be compatible or not ruled out."


def _judge_number(h: _Hit, ctx: Context, sign: Optional[int], known) -> Tuple[str, str]:
    ev = ctx.evidence
    lo, hi = ev.zero_interval
    z = ctx.ci_text()
    g = h.data.get("groups", [])

    if h.category == "interval_level":
        s = g[0]
        x = float(s)
        if "credible" in h.phrase:
            return CHECK, ("This result has a frequentist confidence interval, not a Bayesian credible interval; "
                           "the two are interpreted differently.")
        levels = {round(ev.zero_level * 100, 6)}
        if ev.equivalence_level is not None:
            levels.add(round(ev.equivalence_level * 100, 6))
        if any(_close(x, s, q) for q in levels):
            return CONSISTENT, "Matches an interval level used in this result."
        have = " and ".join(f"{q:g}%" for q in sorted(levels, reverse=True))
        return CHECK, f"This result uses {have} intervals; a {s}% interval was not computed."

    if h.category == "alpha_level":
        s = next(x for x in g if x is not None)
        x = float(s)
        value = x / 100 if "%" in h.phrase else x
        if _close(value, s, ev.alpha) or ("%" in h.phrase and _close(x, s, ev.alpha * 100)):
            return CONSISTENT, "Matches the declared alpha."
        if "%" in h.phrase and _close(x, s, (1 - ev.alpha) * 100):
            return CONSISTENT, "Matches the confidence level."
        return CHECK, f"The declared alpha is {fmt(ev.alpha)}."

    if h.category == "p_value":
        op, s = g[0].strip(), g[1]
        x = float(s)
        named, elsewhere = h.data.get("named"), h.data.get("named_elsewhere")
        if named == "ambiguous":
            return CHECK, "This part names more than one test, so statwarrant cannot tell which p-value is meant."
        tests = {None: ("zero test", ev.p_zero), "equivalence": ("equivalence test", ev.p_equivalence),
                 "minimal-effect": ("minimal-effect test", ev.p_minimal_effect)}
        name, q = tests[named]
        if q is None:
            return CHECK, f"No {name} was run: no smallest effect size of interest was declared."

        # A converted zero is not an exact probability. Also do not turn a
        # nonzero decimal literal below the binary64 domain into zero (even if
        # it rounds up to the minimum subnormal), or overflow it to infinity.
        if q == 0:
            return CHECK, f"The {name} p-value underflowed or is unavailable; its zero is not exact. Check this comparison."
        try:
            written = Decimal(s)
            if not math.isfinite(x) or (written != 0 and abs(written) < Decimal.from_float(math.ulp(0.0))):
                return CHECK, "The written p-value threshold is outside the representable binary64 range; check it manually."
        except (InvalidOperation, ValueError, OverflowError):
            return CHECK, "The written p-value threshold cannot be represented; check it manually."

        # Near the subnormal boundary, one ulp can be a large share of p.
        # Two-sided p can be normal even though its one-sided sf was subnormal.
        # Tail approximations also have error: guard both sides of the boundary.
        if (op in ("<", "<=", ">", ">=") and min(abs(q), abs(x)) < 2 * sys.float_info.min
                and math.isclose(q, x, rel_tol=1e-8, abs_tol=max(math.ulp(q), math.ulp(x)))):
            return CHECK, "This inequality is too close to an extreme-tail numerical boundary to verify."

        def holds(value: float) -> bool:
            # Inequalities are compared exactly (rounding is the writer's job). Equality must
            # match the written rounding and be within half the value ("p = 0" never matches).
            if op in ("<", "<="):
                return value < x or (op == "<=" and value == x)
            if op in (">", ">="):
                return value > x or (op == ">=" and value == x)
            return x > 0 and _close(x, s, value) and abs(x - value) <= 0.5 * value

        if holds(q):
            return CONSISTENT, f"Matches the p-value of the {name} ({fmt_p(q, 4)})."
        if named is None and elsewhere:
            for other, (oname, oq) in tests.items():
                if other is not None and oq is not None and oq != 0 and holds(oq):
                    return CHECK, (f"Does not match the zero test (p = {fmt_p(q, 4)}) but matches the {oname} named "
                                   f"elsewhere in the sentence (p = {fmt_p(oq, 4)}); name the test next to the p-value.")
        return CONFLICT, f"The {name} gives p = {fmt_p(q, 4)}, which is not {'' if op in ('=', 'of', 'was', 'is', ':') else op + ' '}{s}."

    if h.category == "percentage":
        s = g[0]
        x = float(s)
        signs = [-1] if x < 0 else ([sign] if sign in (1, -1) else [1, -1])
        fx = abs(x) / 100
        abs_ok = any(lo <= t * v <= hi for t in signs for v in (fx, abs(x)))
        if ctx.baseline:
            b = ctx.baseline
            rel = ev.estimate / b
            rlo, rhi = sorted((lo / b, hi / b))
            rel_ok = any(rlo <= t * fx <= rhi for t in signs)
            if not (rel_ok or abs_ok):
                return CONFLICT, (f"{s}% matches neither the relative change compatible with the data "
                                 f"({_fmt_percent(rlo)} to {_fmt_percent(rhi)} of the baseline) nor an absolute change in the {z}.")
            return CHECK, (f"Say whether this is an absolute or a relative change, and report both: "
                             f"absolute {ctx.u(ev.estimate)}, relative {_fmt_percent(rel)} of the baseline {ctx.u(b)}.")
        return CHECK, ("Say whether this is percentage points (absolute) or a relative change, and report both; "
                         "declare a baseline to get both numbers. Without a baseline the percentage cannot be checked.")

    if h.category == "range":
        return _judge_range(h, ctx)

    if h.category == "magnitude":
        qual, s = (g[0] or "").strip(), g[1]
        x = float(s)
        if x < 0:
            dirs = [-1]
        elif sign in (1, -1):
            dirs = [sign]
        else:
            dirs = [1, -1]
        v = abs(x)
        if qual in _LOWER_Q:
            ok = any((d > 0 and lo > v) or (d < 0 and hi < -v) for d in dirs)
            if ok:
                return CONSISTENT, f"The whole {z} lies beyond {s}."
            return CONFLICT, f"The data are compatible with effects in the {z}, including effects smaller than {s}."
        if qual in _UPPER_Q:
            ok = any((d > 0 and hi < v) or (d < 0 and lo > -v) for d in dirs)
            if ok:
                return CONSISTENT, f"The whole {z} lies below {s} in size."
            return CONFLICT, f"The data are compatible with effects in the {z}, including effects larger than {s}."
        if any(_close(d * v, s.lstrip("-"), ev.estimate) for d in dirs):
            return CONSISTENT, f"Matches the estimate ({ctx.u(ev.estimate)}); report the interval too ({z})."
        if any(lo <= d * v <= hi for d in dirs):
            return CHECK, f"{s} lies inside the {z} but is not the estimate ({ctx.u(ev.estimate)})."
        return CONFLICT, f"{s} is outside the {z}."

    if h.category == "fold":
        clause = h.data.get("clause", "")
        if not _RATIO_OBJECT.search(clause):
            return CHECK, (f"'{h.phrase}' states a factor, but its clause does not name the quantity (odds, risk, "
                           f"rate, hazard) that changed, so it was not compared with the result.")
        return _judge_factor(float(g[0]), h.phrase, ctx, clause)

    if h.category == "plausible_value":
        word, s = g[0], g[1]
        x = float(s)
        written_sign = s.strip().startswith("-")
        ends = [("lower", lo, z), ("upper", hi, z)]
        if ev.equivalence_interval is not None and ev.equivalence_level != ev.zero_level:
            elo, ehi = ev.equivalence_interval
            e = ctx.ci_text("equivalence")
            ends += [("lower", elo, e), ("upper", ehi, e)]
        span = f"the data are compatible with effects from {ctx.u(lo)} to {ctx.u(hi)}"
        if word in ("high", "low"):
            # signed: "as high as 2.2" is about the upper end, "as low as" about the lower end
            v = -abs(x) if (sign == -1 and not written_sign) else x
            side = "upper" if word == "high" else "lower"
            for name, q, text in ends:
                if name == side and _close(v, s.lstrip("-"), q) and (v < 0) == (q < 0):
                    return CONSISTENT, f"Matches the {side} end of the {text}."
            if not (lo <= v <= hi or _close(v, s.lstrip("-"), lo) or _close(v, s.lstrip("-"), hi)):
                return CONFLICT, f"{s} is outside the {z}: {span} only."
            return CHECK, f"{s} is not the {side} end of the {z}: {span}."
        # magnitude: "as large as 2.2", "as small as 0.3"
        if word in ("small", "little") and lo <= 0 <= hi:
            return CHECK, f"The {z} includes zero, so the effect could be smaller than {s}: {span}."
        pick = max if word not in ("small", "little") else min
        if x < 0 or sign in (1, -1):
            want = -1 if x < 0 else sign
            cands = [(n, q, t) for n, q, t in ends if (q > 0) == (want > 0)]
        else:
            want = None
            cands = ends
        if cands:
            target = pick(abs(q) for _, q, _ in cands)
            cands = [(n, q, t) for n, q, t in cands if abs(q) == target] + \
                    [(n, q, t) for n, q, t in cands if t != z and abs(q) == pick(abs(q2) for _, q2, t2 in cands if t2 != z)]
        for name, q, text in cands:
            if _close(abs(x), s.lstrip("-"), abs(q)):
                if want is None and q < 0:
                    return CHECK, (f"{s} matches the size of the {name} end of the {text} ({ctx.u(q)}), but the "
                                   f"sentence does not say the effect is negative.")
                return CONSISTENT, f"Matches the {name} end of the {text}: {span}."
        far = max(abs(lo), abs(hi))
        near = 0.0 if lo <= 0 <= hi else min(abs(lo), abs(hi))
        if word not in ("small", "little") and abs(x) > far:
            return CONFLICT, f"{s} is beyond the {z}: {span} only."
        if word in ("small", "little") and abs(x) < near:
            return CONFLICT, f"Effects as small as {s} are ruled out: {span}."
        return CHECK, f"{s} is not an end of the {z}: {span}."

    raise KeyError(h.category)


def _judge_range(h: _Hit, ctx: Context) -> Tuple[str, str]:
    ev = ctx.evidence
    g = [x for x in h.data["groups"] if x is not None]
    sa, sb = g[0], g[1]
    a, b = float(sa), float(sb)
    role = _pair_role(h.data.get("context", ""), h.phrase)

    def same(pair) -> bool:
        return _close(a, sa, pair[0]) and _close(b, sb, pair[1])

    def swapped(pair) -> bool:
        return _close(a, sa, pair[1]) and _close(b, sb, pair[0])

    intervals = [(ev.zero_level, ev.zero_interval)]
    if ev.equivalence_interval is not None and ev.equivalence_level != ev.zero_level:
        intervals.append((ev.equivalence_level, ev.equivalence_interval))

    if role == "interval":
        stated = re.findall(r"(\d+(?:\.\d+)?)\s*%", h.data.get("context", ""))
        if stated:
            want = float(stated[-1])
            named = [(lv, iv) for lv, iv in intervals if abs(lv * 100 - want) < 1e-6]
            if not named:
                return CONFLICT, f"This result has no {stated[-1]}% interval."
            lv, iv = named[0]
            if same(iv):
                return CONSISTENT, f"Matches the {level_text(lv)} interval {fmt_ci(*iv)}."
            for other_lv, other in intervals:
                if other_lv != lv and same(other):
                    return CONFLICT, (f"These are the endpoints of the {level_text(other_lv)} interval; the "
                                      f"{level_text(lv)} interval is {fmt_ci(*iv)}.")
            if swapped(iv):
                return CONFLICT, f"The endpoints are in the wrong order: the {level_text(lv)} interval is {fmt_ci(*iv)}."
            return CONFLICT, f"The {level_text(lv)} interval is {fmt_ci(*iv)}."
        for level, iv in intervals:
            if same(iv):
                return CONSISTENT, f"Matches the {level_text(level)} interval {fmt_ci(*iv)}."
        for level, iv in intervals:
            if swapped(iv):
                return CONFLICT, (f"The endpoints are in the wrong order: the {level_text(level)} interval is "
                                  f"{fmt_ci(*iv)}.")
        have = "; ".join(f"{level_text(lv)} {fmt_ci(*iv)}" for lv, iv in intervals)
        return CONFLICT, f"This is not an interval from this result ({have})."

    if role == "bounds":
        if ev.sesoi is None:
            return CHECK, "No smallest effect size of interest was declared, so these bounds cannot be checked."
        if same(ev.sesoi):
            return CONSISTENT, "Matches the declared bounds."
        return CONFLICT, f"The declared bounds are {fmt_bounds(*ev.sesoi)}."

    lo, hi = ev.zero_interval
    z = ctx.ci_text()
    if role == "compatible":
        if a > b:
            return CHECK, "The range is written from high to low; statwarrant cannot tell what is meant."
        inside = (a >= lo or _close(a, sa, lo)) and (b <= hi or _close(b, sb, hi))
        if inside:
            return CONSISTENT, f"These values lie inside the {z}."
        return CONFLICT, f"Part of this range lies outside the {z}."

    if role == "from_to" and ctx.baseline is not None and _close(a, sa, ctx.baseline):
        change = b - a
        if _close(change, sb, ev.estimate) or _close(b, sb, ctx.baseline + ev.estimate):
            return CONSISTENT, f"Matches the baseline ({fmt(ctx.baseline)}) plus the estimate ({fmt(ev.estimate)})."
        if lo <= change <= hi:
            return CHECK, f"A change of {fmt(change)} lies inside the {z} but is not the estimate ({fmt(ev.estimate)})."
        return CONFLICT, f"A change of {fmt(change)} lies outside the {z}."
    return CHECK, "statwarrant cannot tell what this range refers to."


def _judge_role_number(h: _Hit, role: str, ctx: Context, sign: Optional[int]) -> Tuple[str, str]:
    ev = ctx.evidence
    s = h.phrase
    x = float(s)
    lo, hi = ev.zero_interval
    z = ctx.ci_text()
    if role in ("estimate", "coefficient"):
        # Coefficients carry their own sign, not a direction word elsewhere.
        value = sign * x if (role == "estimate" and x > 0 and sign in (1, -1)) else x
        if role == "coefficient":
            # Compare to the actual written precision, not the generic 0.5% tolerance.
            close = False
            if math.isfinite(value):
                try:
                    written = Decimal(s)
                    exponent = written.as_tuple().exponent
                    close = (abs(exponent) <= 1000 and
                             abs(written - Decimal(str(ev.estimate))) <= Decimal("0.5").scaleb(exponent))
                except ArithmeticError:
                    pass  # Unrepresentable written precision is not a match.
        else:
            close = _close(value, s.lstrip("-"), ev.estimate)
        if close and (value >= 0) == (ev.estimate >= 0):
            return CONSISTENT, f"Matches the estimate ({ctx.u(ev.estimate)})."
        if lo <= value <= hi:
            return CHECK, f"{fmt(value)} lies inside the {z}, but the estimate is {ctx.u(ev.estimate)}."
        return CONFLICT, f"{fmt(value)} is outside the {z}; the estimate is {ctx.u(ev.estimate)}."
    if role == "smallest effect size of interest":
        if ev.sesoi is None:
            return CHECK, "No smallest effect size of interest was declared."
        if any(_close(x, s, q) and (x >= 0) == (q >= 0) for q in ev.sesoi):
            return CONSISTENT, "Matches the declared smallest effect size of interest."
        return CONFLICT, f"The declared bounds are {fmt_bounds(*ev.sesoi)}."
    target = {"standard error": ev.se, "degrees of freedom": ev.df, "baseline": ctx.baseline}[role]
    if target is None:
        return CHECK, f"This result has no {role} to compare with."
    if _close(x, s, target) and (x >= 0) == (target >= 0):
        return CONSISTENT, f"Matches the {role} ({fmt(target)})."
    return CONFLICT, f"The {role} is {fmt(target)}."


_DIRECTION_WORDS = tuple(_DIRECTION)
_DIRECTION_NOUNS = re.compile(r"(?:improvements?|increases?|decreases?|gains?|reductions?|declines?|rises?|drops?|"
                              r"benefits?|harms?)")


def _names_outcome(h: "_Hit", ctx: Context) -> bool:
    """'effect on grade improvement': the noun names what was measured, not a direction."""
    if not _DIRECTION_NOUNS.fullmatch(h.phrase):
        return False
    if h.data.get("in_outcome"):  # inside the declared outcome's own wording
        return True
    before = h.data.get("before", "")
    return bool(re.search(r"(?:effects?|impacts?|differences?|changes?|associations?|influence)\s+"
                          r"(?:on|in|of|for|with)\s+(?:[a-z'-]+\s+){0,2}$", before))


# This is deliberately a small grammar, not entity extraction or natural-language
# understanding. Anything outside it must not acquire a sign by substring match.
_THRESHOLD_NAME = r"(?:the\s+)?(?:smallest effect size of interest|sesoi|threshold of interest)\b"
_COMPARISON = re.compile(r"(?<!more )(?<!less )\bthan\b(?!\s+" + _THRESHOLD_NAME + r")|"
                         r"\b(?:versus|vs\.?|compared\s+(?:to|with)|relative\s+to|minus|"
                         r"outperform(?:s|ed|ing)?|underperform(?:s|ed|ing)?|outscore(?:s|d|ing)?|beats?)\b|"
                         r"\bbetween\b(?!\s*[-+]?(?:\d|\.\d))|"
                         r"\b(?:more|less)\s+than\s+(?!" + _THRESHOLD_NAME + r"|\d)[a-z]|"
                         r"\bfrom\s+(?![-+]?(?:\d|\.\d))[^;!?]*\bto\s+(?![-+]?(?:\d|\.\d))|"
                         r"\bfrom\s+(?:baseline|day|week|month|year|time)\b|"
                         r"\b(?:post|pre)[- ]?(?:treatment|intervention|test|procedure)\b|"
                         r"\bduring\s+(?:follow[- ]?up|treatment|intervention)\b|"
                         r"\bwith\s+(?:the\s+)?(?:treatment|intervention|control)\b|"
                         r"\b(?:after|before|following)\b|\bfor\s+(?!display\b)(?:the\s+)?[a-z]")
_IMPLICIT_COMPARATIVE = re.compile(r"\b(?:higher|lower|greater|fewer|better|worse|superior|inferior)\b")
_DIRECT_SIGN = re.compile(r"\s*(?:the\s+)?(?:estimated\s+)?(?:effect(?:\s+estimate)?|difference|estimate|contrast|coefficient)\s+"
                          r"(?:is|was)\s+(?:positive|negative)\s*[.!?]?\s*")
_DIRECT_SIGN_SIGNIFICANCE = re.compile(
    r"\s*(?:the\s+)?(?:estimated\s+)?(?:effect(?:\s+estimate)?|difference|estimate|contrast|coefficient)\s+"
    r"(?:is|was)\s+(?:positive|negative)\s+and\s+(?:statistically\s+)?significant\s*[.!?]?\s*"
)
_DIRECT_SLOPE_SIGN = re.compile(r"\s*(?:the\s+)?(?:estimated\s+)?slope\s+"
                                r"(?:is|was)\s+(?:positive|negative)\s*[.!?]?\s*")
_LABEL = re.compile(r"[a-z0-9]+(?:\s+[a-z0-9]+){0,3}")
_LABEL_STOP = re.compile(r"\b(?:and|or|not|no|never|neither|nor|without|than|from|to|for|is|was|"
                         r"were|are|minus|versus|vs|compared)\b")


def _exact_comparison(text: str, ctx: Context):
    """Return a contrast-oriented sign and matched spans for a few exact sentences.

    Both full labels and the whole sentence must match. The declared contrast is
    user-supplied text, not proof that the labels, outcome or data are correct.
    """
    if not ctx.contrast or not ctx.comparison_origin_is_zero:
        return None
    contrast = _normalize(ctx.contrast)[0].strip()
    pair = re.fullmatch(r"(.+?)\s+minus\s+(.+)", contrast)
    if pair is None:
        return None
    labels = [re.sub(r"\s+", " ", s.strip()) for s in pair.groups()]
    if (labels[0] == labels[1] or any(not _LABEL.fullmatch(s) or _LABEL_STOP.search(s) or
                                      _sign_of(s, ctx.better) is not None for s in labels)):
        return None

    def literal(s):
        return r"\s+".join(re.escape(w) for w in s.split())

    if not ctx.outcome:
        return None
    outcome = _normalize(ctx.outcome)[0].strip()
    if not _LABEL.fullmatch(outcome) or _LABEL_STOP.search(outcome) or _sign_of(outcome, ctx.better) is not None:
        return None
    subject = r"(?:the\s+)?" + literal(outcome)
    ending = r"\s*[.!?]?\s*"
    for first_index, second_index in ((0, 1), (1, 0)):
        first, second = literal(labels[first_index]), literal(labels[second_index])
        a, b = r"(?P<first>" + first + r")", r"(?P<second>" + second + r")"
        # Direction refers to the first group in 'higher for A than for B',
        # but to the destination in 'increased from A to B'.
        patterns = [
            (subject + r"\s+(?:is|are|was|were)\s+(?P<word>higher|lower)\s+for\s+" + a + r"\s+than\s+for\s+" + b,
             first_index),
            (subject + r"\s+(?P<word>increased|decreased|rose|fell)\s+from\s+" + a + r"\s+to\s+" + b,
             second_index),
        ]
        for pattern, oriented_index in patterns:
            match = re.fullmatch(r"\s*" + pattern + ending, text)
            if match:
                token_sign = _sign_of(match.group("word"), ctx.better)
                sign = token_sign if oriented_index == 0 else -token_sign
                return sign, match.span("word"), (match.span("first"), match.span("second"))
    return None


_NUMBER_CATS = {"interval_level", "alpha_level", "p_value", "percentage", "magnitude", "range", "plausible_value",
                "fold"}
_FOLDED = {"importance", "big", "significance"}
_NEGATING = {"nonsignificance", "evidence_absent", "marginal"}


_ACTION = {
    "no_effect": "Report the interval instead, or an equivalence claim if equivalence was tested and established.",
    "nonsignificance": "Add the interval so readers do not read this as 'no effect'.",
    "evidence_absent": "Add the interval so readers do not read this as 'no effect'.",
    "evidence": "Report the p-value and interval rather than a strength label.",
    "marginal": "Report the interval; do not describe a non-significant result as nearly significant.",
    "equivalence": "Claim equivalence only within the declared bounds, and only if the equivalence test establishes it.",
    "small": "Compare the interval with the declared smallest effect size of interest.",
    "importance": "Compare the interval with the declared smallest effect size of interest.",
    "big": "Describe the size with the interval rather than an adjective.",
    "significance": "Check the zero test and the direction.",
    "nonzero": "Check the zero test.",
    "generalization": "Limit the claim to the declared scope and to the average effect.",
    "certainty": "Replace certainty wording with the interval.",
    "causal": "Check that the design supports causal language (randomisation, no confounding).",
    "vague_result": "State the direction, the interval and what was tested.",
    "subgroup": "Analyse the subgroup or group separately before claiming anything about it.",
    "bayesian_wording": "Use frequentist wording for a confidence interval, or run a Bayesian analysis.",
    "probability_misreading": "Rephrase: the interval or p-value does not give this probability.",
    "direction": "Check the direction against the interval.",
    "interval_level": "Report the interval actually computed.",
    "alpha_level": "Report the alpha actually declared.",
    "p_value": "Copy the p-value from the result.",
    "percentage": "State whether the change is absolute or relative, and report both.",
    "magnitude": "Report the estimate and its interval.",
    "unverified_number": "Check this number by hand, or name what it is (estimate, interval, standard error...).",
    "reported_number": "Copy the number from the result.",
    "range": "Copy the interval from the result, lower end first.",
    "unattached_negation": "Check the negated part by hand.",
    "neither_equivalence": "Check both negated claims and their bounds against the result.",
    "neither_established": "Check each part against the result.",
    "ratio": "Report the estimate and interval; state ratios only on a ratio (log) scale or with a baseline.",
    "fold": "Report the estimate and interval; state ratios only on a ratio (log) scale or with a baseline.",
    "plausible_value": "Name the interval and its level, e.g. 'the 95% CI reaches 2.5'.",
}


def check_sentence(sentence: str, ctx: Context) -> CheckResult:
    """Look for possible problems in one English sentence. Never approves the sentence."""
    hits, residual, covered, idx, original = _scan(sentence, ctx)
    known = _known(ctx)

    # The scanner normally treats these words as qualifiers, not direction
    # carriers. In an explicit comparison they still need human review.
    for m in re.finditer(r"\b(?:more|less|larger|smaller)\b", original):
        if not any(h.start <= m.start() and m.end() <= h.end for h in hits):
            if re.match(r"\s+than\s+" + _THRESHOLD_NAME, original[m.end():]):
                continue
            hits.append(_Hit("comparison_unbound", m.group(), m.start(), m.end()))
            residual = _blank(residual, m.start(), m.end())
            for k in range(m.start(), m.end()):
                covered[k] = True

    direction_hits = [h for h in hits if (h.category in _DIRECTION_WORDS and not _names_outcome(h, ctx)) or
                      (h.category == "small" and _sign_of(h.phrase, ctx.better) is not None)]
    embedded = [h for h in hits if h.category in ("no_effect", "not_established", "not_ruled_out", "compatible",
                                                   "cannot_judge", "nonsignificance", "evidence_absent", "marginal")
                and _sign_of(h.phrase, ctx.better) is not None]
    comparison = _exact_comparison(original, ctx)
    if comparison and (len(direction_hits) != 1 or
                       (direction_hits[0].start, direction_hits[0].end) != comparison[1] or embedded):
        comparison = None
    if comparison:
        # Digits within the exactly matched entity labels are names (day 2),
        # not effect estimates. Do not turn them into unverified numbers.
        hits = [h for h in hits if not (h.category == "number" and
                any(a <= h.start and h.end <= b for a, b in comparison[2]))]
    comparison_cue = _COMPARISON.search(original)
    # An ordered comparison can be embedded in a numeric or significance claim
    # even when the scanner has not recognized a directional word (e.g. a
    # reversed signed difference, or "significantly longer ... than ...").
    comparison_sensitive = {"number", "magnitude", "percentage", "range", "significance",
                            "importance", "evidence", "evidence_absent", "marginal"}
    comparison_with_claim = bool(comparison_cue and any(h.category in comparison_sensitive for h in hits))
    has_direction = bool(direction_hits or embedded or comparison_with_claim or
                         any(h.category == "comparison_unbound" for h in hits))
    implicit = any(_IMPLICIT_COMPARATIVE.search(h.phrase) for h in direction_hits + embedded)
    # These exact templates describe the signed result itself, not an inferred
    # group ordering. Preserve the shared build_claims/check_sentence contract.
    summaries = _allowed_templates(ctx)
    if ctx.scope:
        summaries = [f"{summary} Scope: {ctx.scope}." for summary in summaries]
    result_summary = sentence in summaries
    direct_sign = bool(ctx.comparison_origin_is_zero and (
        _DIRECT_SIGN.fullmatch(original) or
        _DIRECT_SIGN_SIGNIFICANCE.fullmatch(original) or
        (_DIRECT_SLOPE_SIGN.fullmatch(original) and re.search(r"\bslope\b", ctx.contrast or "", re.IGNORECASE))
    ))
    # If a comparative cue or declared contrast is present, the sign must be
    # bound to the wording; other unrecognized language can still escape this guard.
    unbound = (has_direction and comparison is None and not result_summary and not direct_sign and
               (not ctx.comparison_origin_is_zero or ctx.contrast is not None or implicit or bool(comparison_cue) or
                len(direction_hits) + len(embedded) > 1 or
                any(h.category == "comparison_unbound" for h in hits)))
    review_reason = ("The direction's relationship to the declared contrast, compared groups or time points "
                     "and their order could not be verified. Check the wording and contrast by hand.")

    def unbound_reason(h: _Hit) -> str:
        # A number or size claim inside an unbound comparison: say what was not checked and
        # why, instead of repeating the direction message.
        what = _UNBOUND_WHAT.get(h.category, "this part")
        if h.category == "number" and h not in embedded:
            what = "this number"
        reason = (f"{_UNBOUND_PREFIX} {what} depends on which way the comparison runs, and the wording could not "
                  f"be tied to the declared contrast ({ctx.contrast or 'none declared'}). Check it by hand.")
        if h.category == "percentage":
            reason += " Also say whether the percentage is absolute (percentage points) or relative."
        return reason

    def segment(pos: int) -> int:
        return sum(1 for _ in _SEGMENT.finditer(original, 0, pos))

    def judge(h: _Hit):
        if h.category == "number":
            role = _number_hit_role(h, original, ctx)
            return None if role is None else _judge_role_number(h, role, ctx, sign)
        if h.category in _NUMBER_CATS:
            return _judge_number(h, ctx, sign, known)
        return _judge_hit(h, ctx, sign)

    def judge_with_safeguards(h: _Hit):
        if h.category == "comparison_unbound":
            return CHECK, review_reason
        if unbound:
            role = _number_hit_role(h, original, ctx) if h.category == "number" else None
            if (h in embedded or h.category in ("importance", "big", "significance", "nonsignificance", "evidence",
                                                "evidence_absent", "marginal", "small", "magnitude", "percentage",
                                                "range", "ratio", "fold", "plausible_value")
                    or role in ("estimate", "coefficient")):
                details = []
                if h.data.get("multiple_models"):
                    details.append("More than one model is mentioned; verify which model this number describes.")
                if "unit" in h.data:
                    declared = _SIMPLE_UNITS.get((ctx.units or "").strip().lower())
                    if h.data.get("unit_compound") or declared is None or h.data["unit"] != declared:
                        details.append("Also check the written and declared units and any conversion by hand.")
                return CHECK, " ".join([review_reason if h in embedded else unbound_reason(h)] + details)
        verdict = judge(h)
        if verdict is None:
            return None
        status, reason = verdict
        if h.data.get("pp"):
            reason += " (Read as percentage points of a proportion.)"
        if h.data.get("pp_units"):
            return CHECK, (f"Percentage points cannot be converted to the declared units "
                           f"({ctx.units or 'none declared'}). State the value on the scale of the analysis, or "
                           f"declare proportion units such as 'accuracy'.")
        if h.data.get("pp_alt") and status == CONFLICT:
            alt = _Hit(h.category, h.phrase, h.start, h.end, dict(h.data))
            _rescale(alt)
            alt_verdict = judge(alt)
            if alt_verdict is not None and alt_verdict[0] != CONFLICT:
                return CHECK, (f"{reason} Read as percentage points it would fit; say which scale this number "
                               f"is on.")
        if (h.category in ("p_value", "significance", "nonsignificance", "evidence_absent", "marginal")
                and status == CONSISTENT and h.data.get("named") is None and h.data.get("named_elsewhere")):
            return CHECK, (f"{reason} But this clause also names another test, so statwarrant cannot be sure "
                           f"this refers to the test of difference from zero; name the test next to it.")
        if "unit" in h.data:
            declared = _SIMPLE_UNITS.get((ctx.units or "").strip().lower())
            stated = h.data["unit"]
            if h.data["multiple_models"]:
                return CHECK, ("More than one model is mentioned; this quantity's connection to this result "
                               "has not been verified. Check the number and unit against the intended model.")
            if h.data["unit_compound"] or declared is None or stated is None:
                return CHECK, ("The written or declared units are missing, compound, or not supported by the "
                               "simple-unit pattern. Check the quantity and its scale by hand.")
            if stated != declared:
                return CHECK, (f"The adjacent unit ({stated}) differs from the declared unit ({ctx.units}). "
                               "The number has not been compared across scales; check the unit and any conversion by hand.")
            if status == CONSISTENT:
                reason += " The adjacent simple unit matches the declared unit."
        elif status == CONSISTENT and (h.category == "magnitude" or
                                       (h.category == "number" and _number_role(h.data.get("context", "")) == "estimate")):
            if not h.data.get("pp"):
                reason += " This is a numeric comparison only; any adjacent unit may be unchecked."
        return status, reason

    def part(cat: str, hs: List[_Hit], status: str, reason: str) -> Tuple[int, Part]:
        pieces = sorted({(a, b) for _, a, b in (_span(sentence, idx, h.start, h.end) for h in hs) if a >= 0})
        text = " … ".join(sentence[a:b] for a, b in pieces)
        action = _ACTION.get(cat, "Check this statement against the result.") if status != CONSISTENT else ""
        if status == CHECK and (reason == review_reason or reason.startswith(_UNBOUND_PREFIX)):
            action = "Verify the compared groups or time points, their order and the declared contrast by hand."
        if status == CHECK and any("unit_span" in h.data for h in hs):
            action = "Check the intended quantity, unit and any conversion by hand."
        rule = "direction" if cat == "comparison_unbound" else cat.replace("_", "-")
        return min(h.start for h in hs), Part(rule, text, status, reason, action, tuple(pieces))

    # The direction the sentence asserts (negated phrases do not count). Size
    # phrases such as "a small increase" carry a direction too.
    signs = set()
    carriers = []
    for h in hits:
        if h.category in _DIRECTION_WORDS and _names_outcome(h, ctx):
            continue
        if h.category in _DIRECTION_WORDS or h.category == "small":
            sg = _sign_of(h.phrase, ctx.better)
            if sg is not None:
                carriers.append(h)
                signs.update({sg} if sg != 0 else {1, -1})
    sign = None if not signs else (signs.pop() if len(signs) == 1 else 0)
    if unbound:
        sign = None
    elif comparison:
        sign = comparison[0]

    parts: List[Tuple[int, Part]] = []
    unknown = []
    for h in hits:
        if h.category in _DIRECTION_WORDS:
            continue
        verdict = judge_with_safeguards(h)
        if verdict is None:  # a number whose role is not stated
            unknown.append((h, _match_known(float(h.phrase), h.phrase, known)))
            continue
        status, reason = verdict
        pieces = [h]
        if "unit_span" in h.data and status != CONFLICT:
            a, b = h.data["unit_span"]
            if not (h.start <= a and b <= h.end):
                pieces.append(_Hit("unit", original[a:b], a, b))
        parts.append(part("reported_number" if h.category == "number" else h.category, pieces, status, reason))

    if unknown:
        # The number's role (estimate, interval end, standard error...) is not stated, so
        # even a number that equals something in the result is not taken as consistent.
        notes = [f"{h.phrase} may match the {name} after rounding" if name else f"{h.phrase} matches nothing in this result"
                 for h, name in unknown]
        parts.append(part("unverified_number", [h for h, _ in unknown], CHECK,
                          "statwarrant cannot tell what " + ("these numbers stand" if len(unknown) > 1 else
                                                             "this number stands") + " for (" + "; ".join(notes) + ")."))

    folded = any(p.rule.replace("-", "_") in _FOLDED for _, p in parts)
    # "did not significantly improve": direction words under a negation were judged with
    # it. Only words in the negation's own segment are excused; "..., and scores
    # decreased" is still a direction claim.
    negated_segments = {segment(h.start) for h in hits if h.category in _NEGATING}
    carriers = [h for h in carriers if segment(h.start) not in negated_segments]
    affirmative = set()
    for h in carriers:
        sg = _sign_of(h.phrase, ctx.better)
        affirmative.update({sg} if sg != 0 else {1, -1})
    sign = None if not affirmative else (affirmative.pop() if len(affirmative) == 1 else 0)
    if comparison and carriers:
        sign = comparison[0]
    if carriers and (unbound or not folded or sign == 0):
        ev = ctx.evidence
        z = ctx.ci_text()
        if unbound:
            status, reason = CHECK, review_reason
        elif sign == 0:
            status, reason = CONFLICT, "The sentence states both directions at once."
        elif ev.direction == 0:
            status, reason = CONFLICT, f"The direction of the effect is not established: {z} includes zero."
        elif sign != ev.direction:
            status, reason = CONFLICT, f"The data point the other way ({z})."
        else:
            status, reason = CONSISTENT, f"The direction is established ({z})."
        if comparison:
            reason += " Exact wording was matched to the declared contrast and outcome; their accuracy is not verified."
        parts.append(part("direction", sorted(carriers, key=lambda h: h.start), status, reason))

    if parts:
        neg = _NEGATION.search(residual)
        if neg:
            h = _Hit("unattached_negation", neg.group(0).strip(), neg.start(), neg.end())
            parts.append(part("unattached_negation", [h], CHECK,
                              "statwarrant could not attach this negation to a claim it checks."))
            for k in range(neg.start(), neg.end()):
                covered[k] = True

    ordered = tuple(p for _, p in sorted(parts, key=lambda sp: sp[0]))
    # If no pattern is recognized, the entire non-empty sentence is unchecked.
    # An empty list in serialized results must not imply otherwise.
    unchecked = _unchecked(sentence, residual, covered, idx, ctx.units) if ordered else ((sentence,) if sentence.strip() else ())
    return CheckResult(sentence, ordered, unchecked)


# --------------------------------------------------------------------------- #
# The contract
# --------------------------------------------------------------------------- #

_CATALOGUE = [
    "There is no effect.",
    "The effect is practically important.",
    "The effect is large.",
    "The two conditions are equivalent.",
    "The effect is statistically significant.",
    "The effect generalizes to all settings.",
    "The results prove the effect is exactly the estimated value.",
]


def _allowed_templates(ctx: Context) -> List[str]:
    ev = ctx.evidence
    cls = ev.claim_class
    z = ctx.ci_text()
    if ev.sesoi is not None:
        low, high = ev.sesoi
        e = ctx.ci_text("equivalence")

    if cls == "differs_positive":
        return [f"The effect is positive ({z}). Its practical importance cannot be judged without a declared smallest effect size of interest."]
    if cls == "differs_negative":
        return [f"The effect is negative ({z}). Its practical importance cannot be judged without a declared smallest effect size of interest."]
    if cls == "inconclusive_no_sesoi":
        return [f"A difference from zero is not established; the data are compatible with an effect of zero. The {z}."]
    if cls == "exceeds_sesoi_positive":
        return [f"The effect is positive and larger than the smallest effect size of interest ({ctx.bound_u(high)}) ({z})."]
    if cls == "exceeds_sesoi_negative":
        return [f"The effect is negative and larger in magnitude than the smallest effect size of interest ({ctx.bound_u(low)}) ({z})."]
    if cls == "nonzero_negligible":
        return [f"The effect differs from zero but is smaller than the smallest effect size of interest: "
                f"it lies within {fmt_bounds(low, high)} ({e}). It is detectable but practically negligible."]
    if cls == "equivalent":
        return [f"The effect is practically equivalent to zero within {fmt_bounds(low, high)} ({e}). "
                f"A small effect inside these bounds is not ruled out."]
    if cls == "positive_importance_undetermined":
        return [f"The effect is positive ({z}); whether it reaches the smallest effect size of interest "
                f"({ctx.bound_u(high)}) is not determined by these data."]
    if cls == "negative_importance_undetermined":
        return [f"The effect is negative ({z}); whether it reaches the smallest effect size of interest "
                f"({ctx.bound_u(low)}) is not determined by these data."]
    if cls == "inconclusive_one_side":
        return [f"The result is inconclusive: the data are compatible with an effect of zero and with an "
                f"effect beyond the smallest effect size of interest. The {z}."]
    if cls == "inconclusive_at_bound":
        return [f"The result is inconclusive: the data are compatible with an effect of zero. The interval ends "
                f"at the smallest effect size of interest, to numerical precision ({z})."]
    if cls == "inconclusive_both":
        return [f"The result is inconclusive: the data are compatible with an effect of zero and with "
                f"effects beyond the smallest effect size of interest in either direction. The {z}."]
    raise KeyError(cls)


def build_claims(ctx: Context) -> Claims:
    claims = Claims()
    for text in _allowed_templates(ctx):
        if ctx.scope:
            text = f"{text} Scope: {ctx.scope}."
        claims.allowed.append(Claim(text, "allowed", "Matches the position of the interval.", ctx.evidence.claim_class))
    for sentence in _CATALOGUE:
        res = check_sentence(sentence, ctx)
        if res.level == CONFLICT:
            blocked = [p for p in res.parts if p.status == CONFLICT]
            reasons = list(dict.fromkeys(p.reason for p in blocked))
            rules = list(dict.fromkeys(p.rule for p in blocked))
            claims.blocked.append(Claim(sentence, "blocked", " ".join(reasons), ",".join(rules)))

    ev = ctx.evidence
    unresolved = [name for name, p in (("zero test", ev.p_zero), ("equivalence test", ev.p_equivalence),
                                      ("minimal-effect test", ev.p_minimal_effect)) if p is not None and p == 0.0]
    if unresolved:
        claims.notes.append("The p-value for the " + ", ".join(unresolved) + " underflowed or is unavailable in "
                            "binary64; the stored zero is not an exact probability. Check extreme comparisons manually.")
    if ev.level_conflict:
        low, high = ev.sesoi
        claims.notes.append(
            f"Level conflict: equivalence is established with the {level_text(ev.equivalence_level)} interval used by TOST, "
            f"but the {ctx.ci_text()} reaches outside {fmt_bounds(low, high)}. Report both intervals, or use "
            f"interval_policy='single' for one consistent reading."
        )
    if ev.sesoi is None:
        claims.notes.append("No smallest effect size of interest was declared: claims about practical importance "
                            "and equivalence are withheld.")
    if not ctx.scope:
        claims.notes.append("No scope was declared: state the population, data and conditions the result comes from.")
    if ctx.baseline:
        rel = ev.estimate / ctx.baseline
        claims.notes.append(
            f"Report both scales: absolute change {ctx.u(ev.estimate)}, relative change {_fmt_percent(rel)} "
            f"of the baseline {ctx.u(ctx.baseline)}."
        )
    return claims
