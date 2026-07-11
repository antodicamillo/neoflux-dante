"""Config agente: persona nel prompt, iniezione umore, tool consentiti."""

from agent.config import _allowed_tools, system_prompt


def test_system_prompt_has_persona():
    p = system_prompt()
    assert "DANTE" in p and "Capo" in p             # persona JARVIS
    assert "1-2 frasi" in p                          # regola di brevità


def test_system_prompt_injects_mood():
    assert "teso" in system_prompt("teso")


def test_allowed_tools_includes_virtualizor():
    tools = _allowed_tools()
    assert any("virtualizor" in t for t in tools)
    # sono nomi MCP pienamente qualificati
    assert all(t.startswith("mcp__neoflux-") for t in tools)
