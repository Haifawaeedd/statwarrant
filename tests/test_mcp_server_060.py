"""The MCP server, through the real protocol layer (in-memory client). Skipped without mcp."""

import sys

import pytest

mcp = pytest.importorskip("mcp", reason="the MCP server needs the mcp package (Python 3.10+)")
anyio = pytest.importorskip("anyio")

from statwarrant.mcp_server import build_server  # noqa: E402

RESULT = {"estimate": 4.2, "se": 1.6, "df": 58, "sesoi": 3, "sesoi_source": "smallest gain teachers act on",
          "units": "points", "outcome": "exam score", "contrast": "new method minus existing method",
          "scope": "first-year students, one university"}


def _call(tool, args):
    from mcp import Client

    async def go():
        async with Client(build_server()) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            result = await client.call_tool(tool, args)
            # MCP wraps a dict return as {"result": ...}
            data = (result.structured_content or {}).get("result")
            return names, result, data

    return anyio.run(go)


def test_tools_are_listed_and_analyze_returns_the_contract():
    names, result, data = _call("analyze_result", {"result": RESULT})
    assert {"analyze_result", "verify_assertions", "check_sentences"} <= names
    assert data["allowed"][0]["text"].startswith("The effect is positive")
    assert any(b["category"] == "no-effect" for b in data["blocked"])
    assert "## statwarrant report" in data["report_markdown"]


def test_verify_assertions_through_the_protocol():
    claims = [{"kind": "no_effect", "quote": "no effect"},
              {"kind": "nonzero", "direction": "positive", "quote": "improved"},
              {"kind": "important", "quote": "meaningful"}]
    _, _, data = _call("verify_assertions", {"result": RESULT, "assertions": claims})
    statuses = [v["status"] for v in data["verdicts"]]
    assert statuses == ["contradicted", "supported", "not_established"]


def test_check_sentences_and_interval_input():
    r = dict(RESULT, estimate=None, se=None, ci_lower=1.0, ci_upper=7.4)
    _, _, data = _call("check_sentences", {"result": r, "sentences": ["There is no difference between methods."]})
    assert data["checks"][0]["level"] == "conflict"


def test_bad_kind_is_rejected_by_the_schema():
    _, result, _ = _call("verify_assertions", {"result": RESULT, "assertions": [{"kind": "proves"}]})
    assert result.is_error


def test_stdio_entry_point_starts(tmp_path):
    # the console script's module runs as a real stdio server
    from mcp import Client, StdioServerParameters

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "statwarrant.mcp_server"])
        async with Client(params) as client:
            return {t.name for t in (await client.list_tools()).tools}

    assert "verify_assertions" in anyio.run(go)
