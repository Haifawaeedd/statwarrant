"""Optional language-model layer: the model reads, statwarrant decides.

``Result.review(sentence, llm=...)`` asks a language model to turn a sentence into
structured assertions (:mod:`statwarrant.assertions`) and to note what numbers cannot
check (what the measure means, the population named, mechanisms). statwarrant then
judges every assertion with its own tests. The model never decides whether a claim is
warranted, and it is not shown the result's numbers while it reads, so it cannot
"correct" the sentence towards them.

When the sentence has problems the model may also propose a rewrite, built only from
the claim contract's allowed statements. The rewrite is checked again (rules and
assertions) and offered only if nothing in it conflicts with the result.

Any model can be used: :class:`AnthropicLLM`, :class:`OpenAILLM` (also any
OpenAI-compatible server, such as a local model), or :class:`CallableLLM` around your
own function. Nothing is sent anywhere unless you pass a model: the sentence and the
plan's descriptions (outcome, contrast, units, scope, design) go to its provider.

The layer is experimental and its accuracy has not been measured. A review never
approves a sentence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .assertions import CONTRADICTED, KINDS, NOT_ESTABLISHED, TO_VERIFY, Assertion, Verdict
from .claims import CONFLICT, CheckResult

__all__ = ["LLM", "CallableLLM", "AnthropicLLM", "OpenAILLM", "Review", "review"]


class LLM:
    """Anything with ``complete(system, user) -> str``."""

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class CallableLLM(LLM):
    """Wrap a function ``fn(system, user) -> str`` (any provider, any local model)."""

    def __init__(self, fn: Callable[[str, str], str]):
        self.fn = fn

    def complete(self, system: str, user: str) -> str:
        return self.fn(system, user)


class AnthropicLLM(LLM):
    """Claude through the Anthropic API (``pip install "statwarrant[anthropic]"``).

    The API key is read from ANTHROPIC_API_KEY unless given. ``model`` is required, so
    the model used is always stated in your code.
    """

    def __init__(self, model: str, *, api_key: Optional[str] = None, max_tokens: int = 1500, client=None):
        if not model:
            raise ValueError("name the model, e.g. AnthropicLLM(model='...')")
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise ImportError('AnthropicLLM needs the anthropic package: pip install "statwarrant[anthropic]"') from exc
            client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.client, self.model, self.max_tokens = client, model, max_tokens

    def complete(self, system: str, user: str) -> str:
        msg = self.client.messages.create(model=self.model, max_tokens=self.max_tokens, system=system,
                                          messages=[{"role": "user", "content": user}])
        return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "text") == "text")


class OpenAILLM(LLM):
    """OpenAI, or any OpenAI-compatible server via ``base_url`` (``pip install "statwarrant[openai]"``).

    For a local model served by an OpenAI-compatible server (for example Ollama, vLLM or
    llama.cpp), give its ``base_url`` and any non-empty ``api_key`` it accepts.
    """

    def __init__(self, model: str, *, api_key: Optional[str] = None, base_url: Optional[str] = None, client=None):
        if not model:
            raise ValueError("name the model, e.g. OpenAILLM(model='...')")
        if client is None:
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise ImportError('OpenAILLM needs the openai package: pip install "statwarrant[openai]"') from exc
            kwargs = {k: v for k, v in (("api_key", api_key), ("base_url", base_url)) if v}
            client = openai.OpenAI(**kwargs)
        self.client, self.model = client, model

    def complete(self, system: str, user: str) -> str:
        r = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

EXTRACT_SYSTEM = """You read one sentence a researcher wrote about a statistical result and list the claims it \
makes about the effect, as JSON. You do not judge whether the claims are true: a separate program checks them \
against the result, and you are deliberately not shown the numbers.

Return only one JSON object, with no other text:
{"assertions": [{"kind": ..., "direction": ..., "value": ..., "polarity": ..., "quote": ...}],
 "meaning": [{"quote": ..., "concern": ...}]}

kind is one of:
%s

direction: "positive" or "negative" relative to the declared contrast ("positive" means its first term is \
larger), or null. Use the declared preference (whether higher values are better) to read words such as \
"improved", "worse", "reduced". Use null when the sentence states no direction, compares groups that are not \
the declared contrast, or the order is unclear.
value: for at_least, at_most and about, the size as written, as a positive number in the declared units; \
otherwise null. If the number is in other units (percent, standard deviations), use null and add a meaning note.
polarity: "asserted" for a plain claim; "denied" when the sentence says it is false or not shown ("not \
significant", "no evidence that"); "hedged" for "may", "might", "suggests", "a trend towards".
"There is no difference" is kind no_effect, polarity asserted (not nonzero denied).
quote: the exact words of the sentence the item was read from.
List only claims the sentence makes. Do not repeat a claim.

meaning: what numbers cannot check. A construct broader than the declared outcome ("reasoning" when the outcome \
is answer accuracy), a population or setting other than the declared scope, a mechanism, safety, cost, or groups \
that are not part of the contrast. Each item has the quote and a one-sentence concern. Use an empty list if none."""

REWRITE_SYSTEM = """Rewrite one sentence about a statistical result so that it says only what the allowed \
statements support. Keep the author's topic and register, use one or two sentences, copy numbers only from the \
allowed statements, and add no claim they do not make. Return only one JSON object: {"rewrite": "..."}"""


def _extract_system() -> str:
    return EXTRACT_SYSTEM % "\n".join(f"- {k}: {v}" for k, v in KINDS.items())


def _describe_plan(res) -> str:
    p = res.plan
    rows = [("outcome", p.outcome), ("contrast", p.contrast), ("units", p.units),
            ("higher values are", "better" if p.better == "higher" else "worse"),
            ("scope", p.scope), ("design", p.design), ("subgroup", p.subgroup),
            ("estimand", getattr(res, "estimand", None))]
    return "\n".join(f"- {k}: {v if v else 'not stated'}" for k, v in rows)


def extract_prompt(res, sentence: str) -> str:
    return f"Declared description of the result:\n{_describe_plan(res)}\n\nSentence:\n{sentence}"


def rewrite_prompt(res, sentence: str, problems: List[str]) -> str:
    allowed = "\n".join(f"- {c.text}" for c in res.claims.allowed)
    blocked = "\n".join(f"- {c.text} ({c.reason})" for c in res.claims.blocked)
    issues = "\n".join(f"- {x}" for x in problems) or "- none listed"
    return (f"Allowed statements:\n{allowed}\n\nStatements the result does not support:\n{blocked}\n\n"
            f"Problems found in the sentence:\n{issues}\n\nSentence:\n{sentence}")


def parse_json(text: str) -> dict:
    """The first JSON object in a model's reply (tolerates code fences and surrounding text)."""
    if not isinstance(text, str):
        raise ValueError("the model returned no text")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("the model's reply contains no JSON object")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("the model's reply is not a JSON object")
    return data


# --------------------------------------------------------------------------- #
# Review
# --------------------------------------------------------------------------- #

_NO_ASSERTIONS = "the language model's reply had no \"assertions\" list"
_NOT_USED = "the language model could not be used"
_READ_FAILURES = (_NO_ASSERTIONS, _NOT_USED)


@dataclass
class Review:
    """A sentence read by a language model and judged by statwarrant. Never an approval."""

    sentence: str
    rules: CheckResult
    verdicts: List[Verdict] = field(default_factory=list)
    meaning: List[dict] = field(default_factory=list)
    suggestion: Optional[str] = None
    suggestion_rules: Optional[CheckResult] = None
    suggestion_verdicts: List[Verdict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    model: Optional[str] = None

    @property
    def read_ok(self) -> bool:
        """True when the model's reply could be read as claims (an "assertions" list, possibly empty).

        False when the model could not be used or returned no "assertions" list; the review then
        rests on the rule-based check alone, and ``errors`` says why. Report this rate whenever
        a language-model reader is evaluated."""
        return not any(e.startswith(_READ_FAILURES) for e in self.errors)

    @property
    def level(self) -> str:
        """"conflict", "to_verify" or "no_warnings" (not a clearance)."""
        if _has_problem(self.rules, self.verdicts):
            return "conflict"
        if (self.rules.level is not None or self.meaning or self.errors
                or any(v.status == TO_VERIFY for v in self.verdicts)):
            return "to_verify"
        return "no_warnings"

    def to_dict(self) -> dict:
        return {
            "sentence": self.sentence,
            "level": self.level,
            "read_ok": self.read_ok,
            "model": self.model,
            "rules": self.rules.to_dict(),
            "assertions": [v.to_dict() for v in self.verdicts],
            "meaning": list(self.meaning),
            "suggestion": self.suggestion,
            "suggestion_rules": None if self.suggestion_rules is None else self.suggestion_rules.to_dict(),
            "suggestion_assertions": [v.to_dict() for v in self.suggestion_verdicts],
            "errors": list(self.errors),
            "note": "Assertions were read by a language model and judged by statwarrant's tests. "
                    "No warning is not a clearance.",
        }

    def to_markdown(self) -> str:
        head = {"conflict": "conflicts with the result", "to_verify": "parts to verify",
                "no_warnings": "no warnings (not a clearance)"}[self.level]
        lines = [f"- \"{self.sentence}\": {head}"]
        for p in self.rules.parts:
            if p.status != "consistent":
                lines.append(f"  - rule {p.rule}, {p.status}, \"{p.text}\": {p.reason}")
        for v in self.verdicts:
            a = v.assertion
            q = f"\"{a.quote}\" " if a.quote else ""
            lines.append(f"  - read as {a.kind}" + (f" ({a.direction})" if a.direction else "")
                         + (f" {a.value:g}" if a.value is not None else "")
                         + (f", {a.polarity}" if a.polarity != "asserted" else "")
                         + f" {q}→ {v.status}: {v.reason}")
        for m in self.meaning:
            lines.append(f"  - to verify, \"{m.get('quote', '')}\": {m.get('concern', '')}")
        if self.suggestion:
            lines.append(f"  - suggested (checked again, no conflicts found): \"{self.suggestion}\"")
        for e in self.errors:
            lines.append(f"  - note: {e}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_markdown()


def _has_problem(rules: CheckResult, verdicts: List[Verdict]) -> bool:
    # Denials and hedges are never "not_established" (see assertions.verify), so this covers both.
    return rules.level == CONFLICT or any(v.status in (CONTRADICTED, NOT_ESTABLISHED) for v in verdicts)


def _read(res, sentence: str, llm: LLM) -> Tuple[List[Verdict], List[dict], List[str]]:
    errors: List[str] = []
    try:
        data = parse_json(llm.complete(_extract_system(), extract_prompt(res, sentence)))
    except Exception as exc:  # any provider error: fall back to the rules alone
        return [], [], [f"the language model could not be used ({type(exc).__name__}: {exc}); "
                        f"only the rule-based check ran"]
    if not isinstance(data, dict) or not isinstance(data.get("assertions"), list):
        return [], [], ["the language model's reply had no \"assertions\" list, so no claims were read and "
                        "only the rule-based check ran"]
    verdicts: List[Verdict] = []
    for item in data["assertions"]:
        if not isinstance(item, dict):
            errors.append(f"an assertion read by the model was not usable (not an object): {item!r}")
            continue
        try:
            verdicts.append(res.verify(Assertion.from_dict(item)))
        except (TypeError, ValueError, KeyError) as exc:
            errors.append(f"an assertion read by the model was not usable ({exc}): {item!r}")
    meaning = []
    meaning_items = data.get("meaning")
    for item in meaning_items if isinstance(meaning_items, list) else []:
        if isinstance(item, dict) and item.get("concern"):
            meaning.append({"quote": str(item.get("quote", "")), "concern": str(item["concern"])})
    return verdicts, meaning, errors


def review(res, sentence: str, llm: LLM, *, rewrite: bool = True, record: bool = True) -> Review:
    """Read ``sentence`` with ``llm`` and judge what it claims against ``res``. See :meth:`Result.review`."""
    if not isinstance(sentence, str) or not sentence.strip():
        raise ValueError("give a sentence to review")
    rules = res.check(sentence, record=False)  # kept with the review itself, not twice in the report
    verdicts, meaning, errors = _read(res, sentence, llm)
    out = Review(sentence, rules, verdicts, meaning, errors=errors, model=getattr(llm, "model", None))
    if rewrite and _has_problem(rules, verdicts) and out.read_ok:
        problems = [p.reason for p in rules.conflicts] + [v.reason for v in verdicts
                                                         if v.status in (CONTRADICTED, NOT_ESTABLISHED)]
        try:
            candidate = str(parse_json(llm.complete(REWRITE_SYSTEM, rewrite_prompt(res, sentence, problems)))
                            .get("rewrite") or "").strip()
        except Exception as exc:
            candidate = ""
            out.errors.append(f"no rewrite was produced ({type(exc).__name__}: {exc})")
        if candidate:
            again = res.check(candidate, record=False)
            v2, _, e2 = _read(res, candidate, llm)
            if _has_problem(again, v2) or e2:
                out.errors.append("the model's proposed rewrite still conflicts with the result (or could not be "
                                  "read again) and was discarded")
            else:
                out.suggestion, out.suggestion_rules, out.suggestion_verdicts = candidate, again, v2
    return out

