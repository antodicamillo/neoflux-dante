"""Hook di audit: registra ogni esecuzione di tool dopo che è avvenuta."""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import HookContext

from .audit import audit


async def audit_post_tool_use(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
) -> dict[str, Any]:
    audit(
        "post_tool_use",
        tool=input_data.get("tool_name"),
        tool_use_id=tool_use_id,
    )
    return {}
