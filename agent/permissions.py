"""Gate di sicurezza autoritativo di DANTE (hook PreToolUse).

Un hook PreToolUse viene consultato per OGNI chiamata di tool e può decidere
allow/deny — a differenza di `can_use_tool`, che viene scavalcato da eventuali
voci in `allowed_tools`. Questo è quindi l'unico punto di verità del gate.

Fase 1 = SOLA LETTURA:
- CONSENTITI: gli strumenti dei server MCP di Neoflux (`mcp__neoflux-*`, tutti
  read-only per progettazione) e `ToolSearch` (lookup read-only degli schemi,
  necessario alla CLI per caricare i tool MCP; non esegue nulla).
- NEGATO: tutto il resto (shell locale, scritture, web, sub-agenti…).

In Fase 2 questo gate verrà esteso: per gli strumenti di scrittura marcati
restituirà `ask` (approvazione umana) invece di `deny`.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import HookContext

from .audit import audit

ALLOWED_PREFIXES = ("mcp__neoflux-",)
ALLOWED_EXACT = {"ToolSearch"}


def _allow() -> dict[str, Any]:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    }}


def _deny(tool: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"DANTE è in Fase 1 (sola lettura): '{tool}' non è consentito. "
            "Le azioni di scrittura arriveranno in Fase 2, dietro approvazione umana."
        ),
    }}


async def gate_pretooluse(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
) -> dict[str, Any]:
    tool = input_data.get("tool_name", "")
    if tool.startswith(ALLOWED_PREFIXES) or tool in ALLOWED_EXACT:
        return _allow()
    audit("deny", tool=tool, input=input_data.get("tool_input"), reason="phase1-read-only")
    return _deny(tool)
