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

import asyncio
import base64
import io
import os
import secrets
import tempfile
import wave
from pathlib import Path

import httpx

from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
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

# Snapshot infra sempre pronta (poller in background) → risposte rapide senza tool
from mcp_servers import virtualizor_read as _vz

# Lettura leggera dell'umore dalla voce (solo prosodia, numpy). Import difensivo:
# è un segnale cosmetico, non deve mai far cadere la trascrizione se numpy manca.
try:
    from agent.prosody import extract_prosody, mood_phrase as _mood_phrase
except Exception:  # pragma: no cover
    extract_prosody = None
    _mood_phrase = None

# Umore dalla voce: OFF di default (le soglie prosodiche vanno tarate sul mic reale,
# altrimenti danno segnali errati). Riabilita con DANTE_MOOD=1 dopo la calibrazione.
_MOOD_ON = os.environ.get("DANTE_MOOD", "0").lower() not in ("0", "", "false", "off", "no")

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
    return {"ok": True, "auth": bool(_WEB_PASS), "stt": _WHISPER_MODEL}


# ── STT locale (Whisper) — trascrizione sul box, privata, indipendente dal browser ──
_WHISPER_MODEL = os.environ.get("DANTE_WHISPER_MODEL", "small")
_whisper = None
_whisper_lock = asyncio.Lock()


async def _get_whisper():
    global _whisper
    if _whisper is None:
        async with _whisper_lock:
            if _whisper is None:
                from faster_whisper import WhisperModel
                _whisper = await asyncio.to_thread(
                    WhisperModel, _WHISPER_MODEL, device="cpu", compute_type="int8"
                )
    return _whisper


@app.post("/stt")
async def stt(audio: UploadFile = File(...), _auth: bool = Depends(_require_auth)) -> dict:
    raw = await audio.read()
    if not raw:
        return {"text": ""}
    src = tempfile.mktemp(suffix=".webm")
    wav = src + ".wav"
    try:
        with open(src, "wb") as fh:
            fh.write(raw)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", wav,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        model = await _get_whisper()

        def _run() -> str:
            # initial_prompt orienta Whisper sul vocabolario di dominio (acronimi inclusi)
            segments, _info = model.transcribe(
                wav, language="it", beam_size=1, vad_filter=True,
                initial_prompt="Comando per l'assistente DANTE sull'infrastruttura Neoflux: "
                               "VPS, server, Virtualizor, Proxmox, cPanel, nodo, RAM, CPU, disco, "
                               "banda, servizio, container, host.",
            )
            return " ".join(s.text for s in segments).strip()

        text = await asyncio.to_thread(_run)

        # Prosodia → traccia di umore, calcolata sullo STESSO wav 16k mono (costo ~10 ms).
        # Fail-open: qualsiasi errore lascia hint="" e non tocca la trascrizione.
        hint = ""
        if _MOOD_ON and extract_prosody is not None and text:
            try:
                feat = await asyncio.to_thread(extract_prosody, wav, text)
                hint = _mood_phrase(feat)
            except Exception:
                hint = ""
        return {"text": text, "mood_hint": hint}
    finally:
        for p in (src, wav):
            try:
                os.remove(p)
            except OSError:
                pass


# ── TTS: ElevenLabs (qualità JARVIS) come primario, Piper come ripiego locale ──
_EL_KEY = os.environ.get("ELEVENLABS_API_KEY")
_EL_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")  # George (default)
# multilingual_v2 = voce più realistica/espressiva (~1.6s). La voce NON è il collo
# di bottiglia, quindi si può permettere la qualità massima.
_EL_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")

_PIPER_MODEL = os.environ.get(
    "DANTE_PIPER_MODEL",
    str(Path(__file__).resolve().parent.parent / "models" / "it_IT-riccardo-x_low.onnx"),
)
_piper = None
_piper_lock = asyncio.Lock()


async def _get_piper():
    global _piper
    if _piper is None:
        async with _piper_lock:
            if _piper is None:
                from piper import PiperVoice
                _piper = await asyncio.to_thread(PiperVoice.load, _PIPER_MODEL)
    return _piper


async def _tts_elevenlabs(text: str) -> bytes:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{_EL_VOICE}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            url, params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": _EL_KEY, "Content-Type": "application/json"},
            json={"text": text, "model_id": _EL_MODEL, "language_code": "it",
                  # stabilità bassa + un po' di stile = più espressiva/umana
                  "voice_settings": {"stability": 0.35, "similarity_boost": 0.85,
                                     "style": 0.3, "use_speaker_boost": True}},
        )
        r.raise_for_status()
        return r.content


async def _tts_piper(text: str) -> bytes:
    voice = await _get_piper()

    def _run() -> bytes:
        from piper import SynthesisConfig
        cfg = SynthesisConfig(length_scale=1.08)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=cfg)
        return buf.getvalue()

    return await asyncio.to_thread(_run)


@app.post("/tts")
async def tts(payload: dict = Body(...), _auth: bool = Depends(_require_auth)) -> Response:
    text = (payload.get("text") or "").strip()
    if not text:
        return Response(status_code=204)
    if _EL_KEY:
        try:
            return Response(content=await _tts_elevenlabs(text), media_type="audio/mpeg")
        except Exception as exc:  # cloud giù o limite raggiunto → ripiego locale
            print(f"[tts] ElevenLabs fallito ({exc}); uso Piper")
    return Response(content=await _tts_piper(text), media_type="audio/wav")


# ── Snapshot infrastruttura: poller in background, iniettata in ogni turno ──
_snapshot = {"text": ""}


async def _refresh_snapshot() -> str:
    def build() -> str:
        parts = []
        for fn in (_vz.vz_list_servers, _vz.vz_list_vps, _vz.vz_server_loads):
            try:
                parts.append(fn())
            except Exception:
                pass
        return "\n\n".join(p for p in parts if p)
    return await asyncio.to_thread(build)


async def _snapshot_loop() -> None:
    while True:
        try:
            _snapshot["text"] = await _refresh_snapshot()
        except Exception:
            pass
        await asyncio.sleep(30)


@app.on_event("startup")
async def _on_startup() -> None:
    asyncio.create_task(_snapshot_loop())


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
                # Traccia di umore (dalla voce) come contesto effimero, solo per QUESTO turno.
                # Stesso tag "[UMORE UTENTE: ...]" che il system prompt insegna a interpretare.
                # È per-turno (il client ws è persistente, quindi NON va messo nel system prompt,
                # che resterebbe congelato al primo turno). Non è un ordine: solo un indizio.
                hint = (data.get("mood_hint") or "").strip()
                prefix = ""
                snap = _snapshot.get("text", "")
                if snap:
                    prefix += ("[STATO INFRA — aggiornato negli ultimi ~30s. Per domande generali su "
                               "stato/salute di server e VPS rispondi DA QUI, senza usare strumenti. "
                               "Usa gli strumenti SOLO per dettagli specifici non presenti qui sotto.]\n"
                               + snap + "\n\n")
                if hint:
                    prefix += f"[UMORE UTENTE: {hint}]\n"
                payload = prefix + message if prefix else message
                await client.query(payload)
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
