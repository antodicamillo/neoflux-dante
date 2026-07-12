"""Ponte "LLM custom" OpenAI-compatibile per la voce real-time (ElevenLabs Agents).

ElevenLabs Agents gestisce l'audio in tempo reale (ascolto continuo, turni, barge-in)
e per il "cervello" chiama un endpoint OpenAI `/v1/chat/completions` in streaming (SSE).
Qui esponiamo *lo stesso* cervello del /ws: Claude Agent SDK con lo snapshot infra
iniettato, gli strumenti MCP read-only e il gate. ElevenLabs muove solo la voce.

Sicurezza: l'endpoint è raggiungibile dall'esterno (ElevenLabs è cloud), quindi è
protetto da un Bearer token (env DANTE_LLM_TOKEN). Senza token configurato l'endpoint
è disabilitato. Nessun segreto esce: risponde solo testo del cervello.

Verificabile a costo zero (nessun credito ElevenLabs): basta un curl testuale, vedi
in fondo. Il flusso audio si attiva solo quando si collega l'Agent ElevenLabs.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)
from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from agent.config import build_options


def _extract(messages: list[dict]) -> tuple[str, list[tuple[str, str]]]:
    """Dall'array OpenAI ricava (ultimo messaggio utente, storia precedente).
    Ignoriamo i system message del chiamante: la persona di DANTE è la nostra."""
    turns = [(m.get("role"), (m.get("content") or "").strip())
             for m in messages if m.get("role") in ("user", "assistant") and m.get("content")]
    last_user = ""
    for i in range(len(turns) - 1, -1, -1):
        if turns[i][0] == "user":
            last_user = turns[i][1]
            history = turns[:i]
            return last_user, history
    return "", turns


def _build_prompt(messages: list[dict], snapshot: str) -> str:
    """Ricostruisce il prompt di un turno: snapshot + breve storia + ultimo messaggio.
    ElevenLabs manda tutta la storia a ogni turno, quindi il client è stateless per
    richiesta (niente stato da gestire lato nostro)."""
    last_user, history = _extract(messages)
    parts: list[str] = []
    if snapshot:
        parts.append("[STATO INFRA — aggiornato negli ultimi ~30s. Per domande generali su "
                     "stato/salute di server e VPS rispondi DA QUI, senza usare strumenti.]\n"
                     + snapshot)
    if history:
        conv = "\n".join(f"{'Utente' if r == 'user' else 'Tu'}: {c}" for r, c in history[-8:])
        parts.append("[CONVERSAZIONE FINORA]\n" + conv)
    parts.append(last_user or "(l'utente non ha detto nulla)")
    return "\n\n".join(parts)


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _chunk(cid: str, model: str, created: int, delta: dict, finish=None) -> dict:
    return {
        "id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def make_router(get_snapshot: Callable[[], str], token: str | None) -> APIRouter:
    """Costruisce il router del ponte. `get_snapshot` legge lo snapshot infra corrente;
    `token` è il Bearer richiesto (se None/"" il ponte è disattivato)."""
    router = APIRouter()

    def _auth(authorization: str | None) -> None:
        if not token:
            raise HTTPException(status_code=503, detail="ponte LLM disattivato (manca DANTE_LLM_TOKEN)")
        expected = f"Bearer {token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="token non valido")

    async def _run(prompt: str):
        """Interroga il cervello e restituisce i pezzi di testo man mano che arrivano."""
        async with ClaudeSDKClient(options=build_options()) as client:
            await client.query(prompt)
            async for m in client.receive_response():
                if isinstance(m, AssistantMessage):
                    for block in m.content:
                        if isinstance(block, TextBlock) and block.text:
                            yield block.text
                elif isinstance(m, ResultMessage):
                    return

    @router.post("/v1/chat/completions")
    async def chat_completions(
        body: dict = Body(...),
        authorization: str | None = Header(default=None),
    ):
        _auth(authorization)
        messages = body.get("messages") or []
        model = body.get("model") or "dante"
        stream = bool(body.get("stream"))
        prompt = _build_prompt(messages, get_snapshot())
        cid = f"chatcmpl-{int(time.time() * 1000)}"
        created = int(time.time())

        if stream:
            async def gen():
                yield _sse(_chunk(cid, model, created, {"role": "assistant"}))
                try:
                    async for piece in _run(prompt):
                        yield _sse(_chunk(cid, model, created, {"content": piece}))
                except Exception as exc:  # non far cadere lo stream: chiudilo pulito
                    yield _sse(_chunk(cid, model, created,
                                      {"content": f" (errore interno: {type(exc).__name__})"}))
                yield _sse(_chunk(cid, model, created, {}, finish="stop"))
                yield "data: [DONE]\n\n"
            return StreamingResponse(gen(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache",
                                              "X-Accel-Buffering": "no"})

        # Non-streaming (comodo per i test): raccoglie tutto e risponde in un colpo.
        text = ""
        async for piece in _run(prompt):
            text += piece
        return JSONResponse({
            "id": cid, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
        })

    return router
