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
from dataclasses import dataclass, field
from decimal import Decimal
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

    def __str__(self) -> str:
        n = len(self.warnings)
        tag = {"warnings": f"{n} warning{'s' if n != 1 else ''}", "no_warnings": "no warnings",
               "no_supported_pattern": "no supported pattern detected"}[self.status]
        lines = [f"[{tag}] {self.sentence}"]
        if self.label:
            lines.append(f"  Checked against result: {self.label}")
        if not self.parts:
            lines.append("  " + _NO_PATTERN_NOTE)
            return "\n".join(lines)
        for p in self.warnings:
            lines.append(f"  - {p.status:<8} {p.rule:<22} \"{p.text}\": {p.reason}")
            if p.action:
                lines.append(f"    Check: {p.action}")
        ok = [p for p in self.parts if p.status == CONSISTENT]
        if ok:
            lines.append("  Consistent with the result: " + "; ".join(f"\"{p.text}\" ({p.rule})" for p in ok) + ".")
        if self.unchecked:
            lines.append("  Not checked: " + ", ".join(f"\"{u}\"" for u in self.unchecked) + ".")
        if self.status == "no_warnings":
            lines.append("  No warning is not a clearance: only the recognised parts were checked.")
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
            "consistent": [p.to_dict() for p in self.parts if p.status == CONSISTENT],
            "unchecked": list(self.unchecked),
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

    def u(self, x: float) -> str:
        return f"{fmt(x)} {self.units}" if self.units else fmt(x)

    def ci_text(self, which: str = "zero") -> str:
        ev = self.evidence
        if which == "equivalence" and ev.equivalence_interval is not None:
            lo, hi = ev.equivalence_interval
            level = ev.equivalence_level
        else:
            lo, hi = ev.zero_interval
            level = ev.zero_level
        return f"{level_text(level)} CI [{fmt(lo)}, {fmt(hi)}]"


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

_WORD_PATTERNS = [
    ("_skip", r"\bfalse (?:positives?|negatives?)\b|\bscope:"),
    # naming a procedure is not a claim about its outcome
    ("_skip", r"\b(?:equivalence|minim(?:al|um)[- ]effects?) (?:and|or) (?:equivalence|minim(?:al|um)[- ]effects?) "
              r"(?:tests?|testing|analys[ie]s)\b"),
    ("_skip", r"\b(?:equivalence|minimal[- ]effects?|non-?inferiority) (?:tests?|testing|analys[ie]s|procedures?|"
              r"bounds?|margins?|regions?)\b|\btost\b"),
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
              r"\b" + _NOUNS + r"\s+(?:is|was|were|are|remained|remains|seems?|seemed|appears?|appeared)\s+"
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
                  r"\b(?:ineffective|unaffected|unchanged)\b|"
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

_NUM = r"-?\d*\.?\d+(?:e-?\d+)?"
_NUMBER_PATTERNS = [
    # "95% probability", "95% confident": a probability statement, not a percentage change
    ("_skip", re.compile(r"(?<![a-z_])" + _NUM + r"\s*%(?=\s*(?:probability|chance|likelihood|confident|confidence|"
                         r"certain|sure)\b)")),
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
            if name != "_skip":
                # context: the words before the match and inside it, up to its first number
                first = min((m.start(i) for i in range(1, (m.lastindex or 0) + 1) if m.group(i) is not None),
                            default=m.start())
                context = original[max(0, m.start() - 60):first]
                named, elsewhere = _named_test(original, m.start(), m.end())
                hits.append(_Hit(name, m.group(0).strip(), m.start(), m.end(),
                                 {"groups": list(m.groups()), "context": context, "named": named,
                                  "named_elsewhere": elsewhere}))
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
        hits.append(_Hit("number", m.group(0), m.start(), m.end(),
                         {"context": original[max(0, m.start() - 60):m.start()]}))
        blank(m.start(), m.end())
    for m in list(re.finditer("%", text)):
        blank(m.start(), m.end())

    for name, pat in _COMPILED:
        for m in list(pat.finditer(text)):
            if name != "_skip":
                named, elsewhere = _named_test(original, m.start(), m.end())
                hits.append(_Hit(name, m.group(0).strip(), m.start(), m.end(),
                                 {"before": original[max(0, m.start() - 40):m.start()], "named": named,
                                  "named_elsewhere": elsewhere, "orig": _span(sentence, idx, m.start(), m.end())[0],
                                  "in_outcome": any(a <= m.start() and m.end() <= b for a, b in outcome_spans)}))
            blank(m.start(), m.end())

    # "0.9 percentage points" about a result stored as a proportion (0.009): read the
    # sentence's outcome-scale numbers on the stored scale.
    mode = _percentage_points(original, ctx)
    if mode:
        after_pp = [m.end() - 1 for m in re.finditer(_PP + r"\s*\(", original)]  # the "(" after "points"
        for h in hits:
            if h.category not in ("magnitude", "range", "number"):
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


def _unchecked(sentence: str, text: str, covered: List[bool], idx: List[int], units: Optional[str]) -> Tuple[str, ...]:
    """Runs of the sentence that no rule looked at and that contain a content word."""
    stop = set(_STOP)
    if units:
        for w in re.findall(r"[a-z][a-z'\-]*", units.lower()):
            stop.update({w, w.rstrip("s"), w.rstrip("s") + "s"})
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


def _judge_hit(h: _Hit, ctx: Context, sign: Optional[int]) -> Tuple[str, str]:
    ev = ctx.evidence
    has_sesoi = ev.sesoi is not None
    lo, hi = ev.zero_interval
    z = ctx.ci_text()
    cat = h.category

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
            return CONFLICT, (f"Equivalence rules out effects outside [{fmt(low)}, {fmt(high)}], not every effect. "
                             f"Say the effect is practically equivalent within these bounds.")
        return CONFLICT, (f"A non-significant result is not evidence of no effect: the data are compatible with "
                         f"effects from {ctx.u(lo)} to {ctx.u(hi)} ({z}).")

    named = h.data.get("named")
    if named in ("equivalence", "minimal-effect", "ambiguous") and cat in (
            "significance", "nonsignificance", "evidence_absent", "marginal"):
        return _judge_named_test(cat, named, ctx)

    if cat in ("nonsignificance", "evidence_absent"):
        if ev.differs_from_zero and sign in (1, -1) and ev.direction == -sign:
            return CHECK, (f"Literally true, but the result is significant in the opposite direction ({z}, "
                             f"p = {fmt(ev.p_zero)}). Say that directly.")
        if ev.differs_from_zero:
            return CONFLICT, f"The result is statistically significant ({z}, p = {fmt(ev.p_zero)})."
        return CHECK, (f"Literally true, but readers often take it to mean 'no effect'. Add the interval: "
                         f"effects from {ctx.u(lo)} to {ctx.u(hi)} remain compatible with the data.")

    if cat == "evidence":
        strong = re.match(r"(?:strong|clear|robust|compelling|convincing|conclusive|solid|good)\b", h.phrase)
        weak = re.match(r"(?:weak|limited|some|modest|suggestive|moderate|tentative|preliminary)\b", h.phrase)
        if weak:
            return CHECK, (f"statwarrant does not grade evidence strength. The zero test gives p = {fmt(ev.p_zero)} "
                             f"({z}); report that instead of a label.")
        if not ev.differs_from_zero:
            return CONFLICT, f"A difference from zero is not established ({z}, p = {fmt(ev.p_zero)})."
        if strong:
            return CHECK, (f"The zero test rejects (p = {fmt(ev.p_zero)}), but statwarrant does not grade how strong "
                             f"the evidence is. Report the p-value and interval ({z}).")
        return CONSISTENT, f"The zero test rejects ({z}, p = {fmt(ev.p_zero)})."

    if cat == "marginal":
        if ev.differs_from_zero:
            return CHECK, f"The result is significant ({z}, p = {fmt(ev.p_zero)}); 'marginal' understates it."
        return CONFLICT, (f"The difference from zero is not significant (p = {fmt(ev.p_zero)}). 'Marginally significant' "
                         f"invites reading it as an effect; report the interval ({z}).")

    if cat == "equivalence":
        if not has_sesoi:
            return CONFLICT, "No smallest effect size of interest was declared, so equivalence cannot be assessed."
        low, high = ev.sesoi
        if ev.equivalent:
            return CONSISTENT, f"Effects outside [{fmt(low)}, {fmt(high)}] are rejected ({ctx.ci_text('equivalence')})."
        return CONFLICT, (f"Equivalence is not established: the {ctx.ci_text('equivalence')} is not inside "
                         f"[{fmt(low)}, {fmt(high)}].")

    if cat == "small":
        if not has_sesoi:
            return CONFLICT, "No smallest effect size of interest was declared, so 'small' or 'negligible' cannot be assessed."
        low, high = ev.sesoi
        if ev.exceeds_sesoi:
            return CONFLICT, f"The effect exceeds the smallest effect size of interest ({z})."
        if ev.equivalent:
            return CONSISTENT, f"The {ctx.ci_text('equivalence')} lies inside [{fmt(low)}, {fmt(high)}]."
        return CONFLICT, (f"The {z} includes effects beyond the smallest effect size of interest "
                         f"([{fmt(low)}, {fmt(high)}]), so a small effect is not established.")

    if cat in ("importance", "big"):
        if not has_sesoi:
            return CONFLICT, ("No smallest effect size of interest was declared, so practical importance or size "
                             "cannot be assessed.")
        low, high = ev.sesoi
        if not ev.exceeds_sesoi:
            return CONFLICT, (f"The {z} includes values smaller than the smallest effect size of interest "
                             f"([{fmt(low)}, {fmt(high)}]).")
        if sign in (1, -1) and sign != ev.direction:
            return CONFLICT, "The effect exceeds the smallest effect size of interest, but in the opposite direction to the one stated."
        if cat == "importance":
            return CONSISTENT, f"The whole {z} lies beyond the smallest effect size of interest."
        near = lo if ev.direction > 0 else hi
        bound = high if ev.direction > 0 else low
        return CHECK, (f"The effect exceeds the smallest effect size of interest ({z}), which supports 'important', "
                         f"not '{h.phrase}': the end of the interval nearest zero, {fmt(near)}, is "
                         f"{abs(near) / abs(bound):.2f} times the threshold. Describe the size with the interval.")

    if cat == "significance":
        if not ev.differs_from_zero:
            return CONFLICT, f"The difference from zero is not statistically significant ({z}, p = {fmt(ev.p_zero)})."
        if sign in (1, -1) and sign != ev.direction:
            return CONFLICT, "The result is significant, but in the opposite direction to the one stated."
        return CONSISTENT, f"{z} excludes zero (p = {fmt(ev.p_zero)})."

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

    if cat == "certainty":
        return CONFLICT, (f"Statistics does not prove, and the estimate is uncertain: report the interval "
                         f"({z}), not a single exact value.")

    if cat == "causal":
        return CHECK, ("Whether causal wording is warranted depends on the design (randomisation, confounding), "
                         "which statwarrant does not know.")

    if cat == "subgroup":
        return CHECK, ("The result is the average difference between the compared conditions. A claim about one "
                       "group alone, or about a subgroup, needs its own analysis.")

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

    raise KeyError(cat)


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
        return CHECK, f"The {named} test gives p = {q:.4g} against a per-side threshold of {fmt(thr)} ({iv})."
    if says_significant == decided:
        return CONSISTENT, f"The {named} test gives p = {q:.4g} against a per-side threshold of {fmt(thr)} ({iv})."
    return CONFLICT, (f"The {named} test {'does not reject' if says_significant else 'rejects'}: p = {q:.4g} against "
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

        def holds(value: float) -> bool:
            # Inequalities are compared exactly (rounding is the writer's job). Equality must
            # match the written rounding and be within half the value ("p = 0" never matches).
            if op in ("<", "<="):
                return value < x or (op == "<=" and value == x)
            if op in (">", ">="):
                return value > x or (op == ">=" and value == x)
            return x > 0 and _close(x, s, value) and abs(x - value) <= 0.5 * value

        if holds(q):
            return CONSISTENT, f"Matches the p-value of the {name} ({q:.4g})."
        if named is None and elsewhere:
            for other, (oname, oq) in tests.items():
                if other is not None and oq is not None and holds(oq):
                    return CHECK, (f"Does not match the zero test (p = {q:.4g}) but matches the {oname} named "
                                   f"elsewhere in the sentence (p = {oq:.4g}); name the test next to the p-value.")
        return CONFLICT, f"The {name} gives p = {q:.4g}, which is not {'' if op in ('=', 'of', 'was', 'is', ':') else op + ' '}{s}."

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
                                 f"({rlo:+.1%} to {rhi:+.1%} of the baseline) nor an absolute change in the {z}.")
            return CHECK, (f"Say whether this is an absolute or a relative change, and report both: "
                             f"absolute {ctx.u(ev.estimate)}, relative {rel:+.1%} of the baseline {ctx.u(b)}.")
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
            return CONFLICT, f"The data are compatible with effects from {ctx.u(lo)} to {ctx.u(hi)}, including effects smaller than {s}."
        if qual in _UPPER_Q:
            ok = any((d > 0 and hi < v) or (d < 0 and lo > -v) for d in dirs)
            if ok:
                return CONSISTENT, f"The whole {z} lies below {s} in size."
            return CONFLICT, f"The data are compatible with effects from {ctx.u(lo)} to {ctx.u(hi)}, including effects larger than {s}."
        if any(_close(d * v, s.lstrip("-"), ev.estimate) for d in dirs):
            return CONSISTENT, f"Matches the estimate ({ctx.u(ev.estimate)}); report the interval too ({z})."
        if any(lo <= d * v <= hi for d in dirs):
            return CHECK, f"{s} lies inside the {z} but is not the estimate ({ctx.u(ev.estimate)})."
        return CONFLICT, f"{s} is outside the {z}: the data are compatible with effects from {ctx.u(lo)} to {ctx.u(hi)}."

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
                return CONSISTENT, f"Matches the {level_text(lv)} interval [{fmt(iv[0])}, {fmt(iv[1])}]."
            for other_lv, other in intervals:
                if other_lv != lv and same(other):
                    return CONFLICT, (f"These are the endpoints of the {level_text(other_lv)} interval; the "
                                      f"{level_text(lv)} interval is [{fmt(iv[0])}, {fmt(iv[1])}].")
            if swapped(iv):
                return CONFLICT, f"The endpoints are in the wrong order: the {level_text(lv)} interval is [{fmt(iv[0])}, {fmt(iv[1])}]."
            return CONFLICT, f"The {level_text(lv)} interval is [{fmt(iv[0])}, {fmt(iv[1])}]."
        for level, iv in intervals:
            if same(iv):
                return CONSISTENT, f"Matches the {level_text(level)} interval [{fmt(iv[0])}, {fmt(iv[1])}]."
        for level, iv in intervals:
            if swapped(iv):
                return CONFLICT, (f"The endpoints are in the wrong order: the {level_text(level)} interval is "
                                  f"[{fmt(iv[0])}, {fmt(iv[1])}].")
        have = "; ".join(f"{level_text(lv)} [{fmt(iv[0])}, {fmt(iv[1])}]" for lv, iv in intervals)
        return CONFLICT, f"This is not an interval from this result ({have})."

    if role == "bounds":
        if ev.sesoi is None:
            return CHECK, "No smallest effect size of interest was declared, so these bounds cannot be checked."
        if same(ev.sesoi):
            return CONSISTENT, "Matches the declared bounds."
        return CONFLICT, f"The declared bounds are [{fmt(ev.sesoi[0])}, {fmt(ev.sesoi[1])}]."

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
    if role == "estimate":
        value = sign * x if (x > 0 and sign in (1, -1)) else x
        if _close(value, s.lstrip("-"), ev.estimate) and (value >= 0) == (ev.estimate >= 0):
            return CONSISTENT, f"Matches the estimate ({ctx.u(ev.estimate)})."
        if lo <= value <= hi:
            return CHECK, f"{fmt(value)} lies inside the {z}, but the estimate is {ctx.u(ev.estimate)}."
        return CONFLICT, f"{fmt(value)} is outside the {z}; the estimate is {ctx.u(ev.estimate)}."
    if role == "smallest effect size of interest":
        if ev.sesoi is None:
            return CHECK, "No smallest effect size of interest was declared."
        if any(_close(x, s, q) and (x >= 0) == (q >= 0) for q in ev.sesoi):
            return CONSISTENT, "Matches the declared smallest effect size of interest."
        return CONFLICT, f"The declared bounds are [{fmt(ev.sesoi[0])}, {fmt(ev.sesoi[1])}]."
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
_NUMBER_CATS = {"interval_level", "alpha_level", "p_value", "percentage", "magnitude", "range"}
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
}


def check_sentence(sentence: str, ctx: Context) -> CheckResult:
    """Look for possible problems in one English sentence. Never approves the sentence."""
    hits, residual, covered, idx, original = _scan(sentence, ctx)
    known = _known(ctx)

    def segment(pos: int) -> int:
        return sum(1 for _ in _SEGMENT.finditer(original, 0, pos))

    def judge(h: _Hit):
        if h.category == "number":
            role = _number_role(h.data.get("context", ""))
            return None if role is None else _judge_role_number(h, role, ctx, sign)
        if h.category in _NUMBER_CATS:
            return _judge_number(h, ctx, sign, known)
        return _judge_hit(h, ctx, sign)

    def judge_with_safeguards(h: _Hit):
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
        return status, reason

    def part(cat: str, hs: List[_Hit], status: str, reason: str) -> Tuple[int, Part]:
        pieces = sorted({(a, b) for _, a, b in (_span(sentence, idx, h.start, h.end) for h in hs) if a >= 0})
        text = " … ".join(sentence[a:b] for a, b in pieces)
        action = _ACTION.get(cat, "Check this statement against the result.") if status != CONSISTENT else ""
        return min(h.start for h in hs), Part(cat.replace("_", "-"), text, status, reason, action, tuple(pieces))

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
        parts.append(part("reported_number" if h.category == "number" else h.category, [h], status, reason))

    if unknown:
        # The number's role (estimate, interval end, standard error...) is not stated, so
        # even a number that equals something in the result is not taken as consistent.
        notes = [f"{h.phrase} equals the {name}" if name else f"{h.phrase} matches nothing in this result"
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
    if carriers and (not folded or sign == 0):
        ev = ctx.evidence
        z = ctx.ci_text()
        if sign == 0:
            status, reason = CONFLICT, "The sentence states both directions at once."
        elif ev.direction == 0:
            status, reason = CONFLICT, f"The direction of the effect is not established: {z} includes zero."
        elif sign != ev.direction:
            status, reason = CONFLICT, f"The data point the other way ({z})."
        else:
            status, reason = CONSISTENT, f"The direction is established ({z})."
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
    unchecked = _unchecked(sentence, residual, covered, idx, ctx.units) if ordered else ()
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
    lo, hi = ev.zero_interval
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
        return [f"A difference from zero is not established; the data are compatible with effects from {ctx.u(lo)} to {ctx.u(hi)} ({z})."]
    if cls == "exceeds_sesoi_positive":
        return [f"The effect is positive and larger than the smallest effect size of interest ({ctx.u(high)}) ({z})."]
    if cls == "exceeds_sesoi_negative":
        return [f"The effect is negative and larger in magnitude than the smallest effect size of interest ({ctx.u(low)}) ({z})."]
    if cls == "nonzero_negligible":
        return [f"The effect differs from zero but is smaller than the smallest effect size of interest: "
                f"it lies within [{fmt(low)}, {fmt(high)}] ({e}). It is detectable but practically negligible."]
    if cls == "equivalent":
        return [f"The effect is practically equivalent to zero within [{fmt(low)}, {fmt(high)}] ({e}). "
                f"A small effect inside these bounds is not ruled out."]
    if cls == "positive_importance_undetermined":
        return [f"The effect is positive ({z}); whether it reaches the smallest effect size of interest "
                f"({ctx.u(high)}) is not determined by these data."]
    if cls == "negative_importance_undetermined":
        return [f"The effect is negative ({z}); whether it reaches the smallest effect size of interest "
                f"({ctx.u(low)}) is not determined by these data."]
    if cls == "inconclusive_one_side":
        return [f"The result is inconclusive: the data are compatible with an effect of zero and with an "
                f"effect beyond the smallest effect size of interest ({z})."]
    if cls == "inconclusive_at_bound":
        return [f"The result is inconclusive: the data are compatible with an effect of zero, and the interval ends "
                f"at the smallest effect size of interest, to numerical precision ({z})."]
    if cls == "inconclusive_both":
        return [f"The result is inconclusive: the data are compatible with an effect of zero and with "
                f"effects beyond the smallest effect size of interest in either direction ({z})."]
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
    if ev.level_conflict:
        low, high = ev.sesoi
        claims.notes.append(
            f"Level conflict: equivalence is established with the {level_text(ev.equivalence_level)} interval used by TOST, "
            f"but the {ctx.ci_text()} reaches outside [{fmt(low)}, {fmt(high)}]. Report both intervals, or use "
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
            f"Report both scales: absolute change {ctx.u(ev.estimate)}, relative change {rel:+.1%} "
            f"of the baseline {ctx.u(ctx.baseline)}."
        )
    return claims
