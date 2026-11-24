"""statwarrant as an MCP server, for Claude, ChatGPT and other AI assistants.

Install with ``pip install "statwarrant[mcp]"`` (Python 3.10 or later) and run::

    statwarrant-mcp                      # stdio: Claude Desktop, Claude Code, Cursor, VS Code ...
    statwarrant-mcp --http --port 8000   # Streamable HTTP at http://127.0.0.1:8000/mcp

The assistant reads the user's sentence and states its claims as structured assertions;
statwarrant judges them with its tests. The assistant never needs an API key for this:
it does the reading itself, and statwarrant does the deciding. Every tool is read-only and
stateless: each call carries the result it is about.
"""

# No "from __future__ import annotations": MCP builds tool schemas from evaluated annotations
# of models defined inside build_server().
import argparse
import sys
from typing import Any, Dict, List, Literal, Optional

from . import __version__

INSTRUCTIONS = """statwarrant says what a statistical result warrants: which statements it supports, which it \
does not, and why. Use it whenever you write or check a sentence about an estimate with a standard error or \
confidence interval.

Workflow:
1. analyze_result: the claim contract (allowed and blocked statements), the tests and every threshold at once.
2. Before writing or approving a sentence about the result, read it yourself and call verify_assertions with \
each claim it makes (kind, direction relative to the declared contrast, size, polarity, and the quoted words).
3. check_sentences runs statwarrant's own rule-based checker on the exact wording.

Report the outcome faithfully. statwarrant never approves a sentence: "no warnings" is not a clearance, \
"to_verify" items must be passed on to the user, and descriptions such as outcome, contrast, scope and design \
are the user's own text, not verified. Do not call a sentence "verified" or "correct"."""


def _require_mcp():
    try:
        from mcp.server import MCPServer  # noqa: F401
        from pydantic import BaseModel  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SystemExit('The MCP server needs the mcp package (Python 3.10+): pip install "statwarrant[mcp]"') from exc


def build_server():
    """The MCP server object (statwarrant tools registered)."""
    _require_mcp()
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations
    from pydantic import BaseModel, Field

    import statwarrant as sw

    class ResultInput(BaseModel):
        """One effect and the plan it is read under. Give estimate with se, or ci_lower and ci_upper."""

        estimate: Optional[float] = Field(None, description="The estimated effect (contrast as declared).")
        se: Optional[float] = Field(None, description="Its standard error.")
        ci_lower: Optional[float] = Field(None, description="Lower end of a published confidence interval.")
        ci_upper: Optional[float] = Field(None, description="Upper end of a published confidence interval.")
        ci_level: float = Field(0.95, description="Level of that interval.")
        df: Optional[float] = Field(None, description="Degrees of freedom (omit for a normal reference).")
        ratio: bool = Field(False, description="The estimate and interval are an odds/risk/rate/hazard ratio as printed.")
        sesoi: Optional[float] = Field(None, description="Smallest effect size of interest d, meaning (-d, d).")
        sesoi_source: Optional[str] = Field(None, description="Required with sesoi: why this threshold.")
        units: Optional[str] = None
        outcome: Optional[str] = Field(None, description="What was measured, e.g. 'exam score'.")
        contrast: Optional[str] = Field(None, description="What was compared, e.g. 'new method minus old method'.")
        scope: Optional[str] = Field(None, description="Population, data and conditions the result comes from.")
        better: Literal["higher", "lower"] = "higher"
        design: Optional[Literal["randomised", "observational"]] = None
        subgroup: Optional[str] = None
        estimand: Optional[str] = Field(None, description="What quantity the estimate is.")
        alpha: float = 0.05
        interval_policy: Literal["single", "standard"] = "single"
        met_method: Literal["split", "relevance"] = "split"

    class AssertionInput(BaseModel):
        """One claim a sentence makes about the effect, read by you."""

        kind: Literal[tuple(sw.assertions.KINDS)] = Field(  # type: ignore[valid-type]
            ..., description="; ".join(f"{k}: {v}" for k, v in sw.assertions.KINDS.items()))
        direction: Optional[Literal["positive", "negative"]] = Field(
            None, description="Relative to the declared contrast ('positive': its first term is larger); "
                              "null if not stated or unclear.")
        value: Optional[float] = Field(None, description="Size in the declared units, for at_least/at_most/about.")
        polarity: Literal["asserted", "denied", "hedged"] = "asserted"
        quote: Optional[str] = Field(None, description="The exact words the claim was read from.")

    def result_of(r: ResultInput):
        plan = sw.declare(sesoi=r.sesoi, sesoi_source=r.sesoi_source, alpha=r.alpha,
                          interval_policy=r.interval_policy, units=r.units, scope=r.scope, better=r.better,
                          outcome=r.outcome, contrast=r.contrast, design=r.design, subgroup=r.subgroup,
                          met_method=r.met_method)
        kw = {"estimand": r.estimand, "ratio": r.ratio}
        if r.ci_lower is not None or r.ci_upper is not None:
            if r.ci_lower is None or r.ci_upper is None:
                raise ValueError("give both ci_lower and ci_upper")
            return plan.analyze(ci=(r.ci_lower, r.ci_upper), ci_level=r.ci_level, estimate=r.estimate,
                                df=r.df, **kw)
        return plan.analyze(estimate=r.estimate, se=r.se, df=r.df, **kw)

    server = MCPServer("statwarrant", version=__version__, instructions=INSTRUCTIONS,
                       website_url="https://github.com/Haifawaeedd/statwarrant")
    ro = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

    @server.tool(title="Analyze a statistical result", annotations=ro, structured_output=True)
    def analyze_result(result: ResultInput) -> Dict[str, Any]:
        """What a result warrants: allowed and blocked statements with reasons, the zero, equivalence and
        minimal-effect tests, every threshold at once, and a Markdown report. Read-only."""
        res = result_of(result)
        d = res.to_dict()
        return {"allowed": d["claims"]["allowed"], "blocked": d["claims"]["blocked"], "notes": d["claims"]["notes"],
                "evidence": d["evidence"], "thresholds": d["thresholds"], "not_verified": d["not_verified"],
                "report_markdown": res.to_markdown()}

    @server.tool(title="Verify structured claims", annotations=ro, structured_output=True)
    def verify_assertions(result: ResultInput, assertions: List[AssertionInput]) -> Dict[str, Any]:
        """Judge claims you read from a sentence against the result. Each verdict is supported,
        not_established, contradicted or to_verify, with a reason. A verdict concerns the statistical
        proposition only, never the wording of the sentence."""
        res = result_of(result)
        verdicts = [res.verify(a.model_dump()).to_dict() for a in assertions]
        return {"verdicts": verdicts,
                "note": "Verdicts concern the statistical propositions only. They do not approve a sentence."}

    @server.tool(title="Check sentences with the rule-based checker", annotations=ro, structured_output=True)
    def check_sentences(result: ResultInput, sentences: List[str]) -> Dict[str, Any]:
        """statwarrant's own pattern-based checker on exact wording (English). Lists conflicts, parts to
        verify and words not checked. Warnings only: no warning is not a clearance."""
        res = result_of(result)
        return {"checks": [res.check(s, record=False).to_dict() for s in sentences],
                "note": "Warnings only. No warning is not a clearance; unchecked words are listed."}

    return server


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="statwarrant-mcp", description="statwarrant as an MCP server")
    ap.add_argument("--http", action="store_true", help="serve Streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--allowed-host", action="append", default=[],
                    help="public host name(s) clients use, e.g. myspace.hf.space (repeatable)")
    a = ap.parse_args(argv)
    server = build_server()
    if not a.http:
        server.run("stdio")
        return
    from mcp.server.transport_security import TransportSecuritySettings
    if a.allowed_host:
        hosts = a.allowed_host + [f"{h}:*" for h in a.allowed_host] + ["127.0.0.1:*", "localhost:*"]
        security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                             allowed_origins=[f"https://{h}" for h in a.allowed_host])
    elif a.host in ("127.0.0.1", "localhost"):
        security = None
    else:
        print("statwarrant-mcp: serving on a public interface without --allowed-host; DNS rebinding protection "
              "is off. The tools are read-only.", file=sys.stderr)
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    server.run("streamable-http", host=a.host, port=a.port, stateless_http=True, transport_security=security)


if __name__ == "__main__":  # pragma: no cover
    main()
