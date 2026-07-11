"""Gate di sicurezza (Fase 1 read-only): consente solo mcp__neoflux-* + ToolSearch, nega il resto."""

import asyncio

from agent.permissions import gate_pretooluse


def _decide(tool: str) -> str:
    out = asyncio.run(gate_pretooluse({"tool_name": tool, "tool_input": {}}, "id", None))
    return out["hookSpecificOutput"]["permissionDecision"]


def test_allows_mcp_and_toolsearch():
    assert _decide("mcp__neoflux-virtualizor__vz_list_vps") == "allow"
    assert _decide("mcp__neoflux-ssh__host_overview") == "allow"
    assert _decide("ToolSearch") == "allow"


def test_denies_write_and_local_tools():
    for tool in ("Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Read"):
        assert _decide(tool) == "deny", tool
