"""DANTE — server web (FastAPI + WebSocket).

Espone DANTE nel browser: una pagina chat che parla via WebSocket con l'agente
(stesso cervello del REPL, stesse regole read-only e audit).

Avvio:
    ./.venv/bin/python -m uvicorn web.server:app --host 0.0.0.0 --port 8800

Sicurezza: HTTP Basic Auth OBBLIGATORIA. Imposta nel .env:
    DANTE_WEB_USER=neoflux
    DANTE_WEB_PASSWORD=...
Senza password il server rifiuta le richieste (fail-closed): DANTE ha accesso
all'infrastruttura, non va lasciato aperto sulla LAN.
"""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

# import di agent.config: attiva anche il loader del .env (ANTHROPIC/OAUTH + DANTE_WEB_*)
from agent.config import build_options

_STATIC = Path(__file__).resolve().parent / "static"
_WEB_USER = os.environ.get("DANTE_WEB_USER", "neoflux")
_WEB_PASS = os.environ.get("DANTE_WEB_PASSWORD")

app = FastAPI(title="DANTE")
_security = HTTPBasic(auto_error=True)

# Asset statici (three.js, font, ecc.) — pubblici, non sensibili. I dati passano dal /ws autenticato.
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


def _valid(user: str, pwd: str) -> bool:
    if not _WEB_PASS:
        return False
    return secrets.compare_digest(user, _WEB_USER) and secrets.compare_digest(pwd, _WEB_PASS)


def _require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> bool:
    if not _WEB_PASS:
        raise HTTPException(status_code=503, detail="DANTE_WEB_PASSWORD non impostata (fail-closed).")
    if not _valid(credentials.username, credentials.password):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return True


@app.get("/", response_class=HTMLResponse)
def index(_auth: bool = Depends(_require_auth)) -> str:
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "auth": bool(_WEB_PASS)}


def _ws_authorized(websocket: WebSocket) -> bool:
    # Il browser, sulla stessa origine, invia le credenziali Basic anche sull'handshake ws.
    if not _WEB_PASS:
        return False
    header = websocket.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        user, _, pwd = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    return _valid(user, pwd)


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    if not _ws_authorized(websocket):
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()
    try:
        # Un client per connessione: il contesto della conversazione persiste nella sessione.
        async with ClaudeSDKClient(options=build_options()) as client:
            await websocket.send_json({"type": "ready"})
            while True:
                data = await websocket.receive_json()
                message = (data.get("message") or "").strip()
                if not message:
                    continue
                await client.query(message)
                async for m in client.receive_response():
                    if isinstance(m, AssistantMessage):
                        for block in m.content:
                            if isinstance(block, TextBlock):
                                await websocket.send_json({"type": "text", "text": block.text})
                            elif isinstance(block, ToolUseBlock):
                                await websocket.send_json({"type": "tool", "name": block.name})
                    elif isinstance(m, ResultMessage):
                        await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # errore runtime: notifica il client e chiude pulito
        try:
            await websocket.send_json({"type": "error", "text": f"{type(exc).__name__}: {exc}"})
            await websocket.close()
        except Exception:
            pass
