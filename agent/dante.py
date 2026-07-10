"""DANTE — REPL interattivo (Fase 1: Osservatore, sola lettura).

Uso:
    python -m agent.dante

Richiede la CLI `claude` autenticata (usa la stessa auth di Claude Code).
"""

from __future__ import annotations

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from .config import build_options

BANNER = (
    "DANTE — Neoflux ops · Fase 1: Osservatore (sola lettura)\n"
    "Scrivi la tua domanda. 'exit' per uscire.\n"
)


async def _prompt() -> str:
    # input() è bloccante: lo spostiamo su un thread per non fermare il loop.
    return await anyio.to_thread.run_sync(lambda: input("\ntu> "))


async def main() -> None:
    print(BANNER)
    async with ClaudeSDKClient(options=build_options()) as client:
        while True:
            try:
                user = (await _prompt()).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user:
                continue
            if user.lower() in {"exit", "quit", "esci"}:
                break

            await client.query(user)
            print("\nDANTE> ", end="", flush=True)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="", flush=True)
                        elif isinstance(block, ThinkingBlock):
                            pass  # ragionamento nascosto in questa UI
                        elif isinstance(block, ToolUseBlock):
                            print(f"\n  · [{block.name}] {block.input}", flush=True)
                elif isinstance(msg, ResultMessage):
                    print()

    print("A presto. — DANTE")


if __name__ == "__main__":
    anyio.run(main)
