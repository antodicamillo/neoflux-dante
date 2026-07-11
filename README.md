# 🛰️ DANTE

**D**on't **A**sk, **N**othing's **T**ruly **E**xploding — l'**assistente vocale** AI di
**Neoflux**, stile "JARVIS". Ci **parli** e ti **risponde a voce**: osserva l'infrastruttura
(Virtualizor, server Linux) e ti dice come stanno le cose, con un carattere spiritoso.

Costruito su **Claude Agent SDK** + **MCP**. Oggi è un **Osservatore in sola lettura**
(sicuro da usare); le azioni di scrittura arriveranno dietro approvazione umana.

## Com'è fatto
```
Browser (UI voce-first: orb 3D, parli col microfono)
   │ HTTPS + WebSocket
web/server.py (FastAPI, servizio systemd sul box)
   ├─ voce → parlato:  ElevenLabs Scribe   (ripiego locale: Whisper)
   ├─ cervello:        Claude (Agent SDK) + snapshot infra → risposte in ~2s
   ├─ risposta → voce: ElevenLabs "George" (ripiego locale: Piper)
   └─ snapshot: interroga Virtualizor ogni 30s (nodo, VPS live, alert)
        │ MCP (solo lettura)
   Virtualizor Admin API · host SSH
```

## Come si usa (produzione)
Gira come servizio `dante-web` sul ProLiant. Apri nel browser (Chrome/Edge/Brave):
**`https://<IP-box>:8800`** → accedi (Basic Auth) → tocca il microfono → **parla**.

> ⚠️ Il box è in DHCP: l'IP può cambiare. Trovalo con `scripts/box-ip.sh`.
> Consigliato assegnargli un **IP statico / reservation**.

Esempi: *"Come stanno i server?"* · *"Quanta RAM usa wapoo?"* · *"Ci sono allarmi?"*

## Sviluppo / test locale
```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/virtualizor.example.yaml config/virtualizor.yaml   # + credenziali Admin API
python -m agent.dante        # REPL testuale da terminale
```
Auth cervello: CLI `claude` autenticata, oppure `CLAUDE_CODE_OAUTH_TOKEN` (headless).
Test: `python -m pytest tests/ -q`.

## Configurazione (env / .env sul box)
| Variabile | Effetto |
|-----------|---------|
| `CLAUDE_CODE_OAUTH_TOKEN` | auth cervello headless (abbonamento) |
| `ELEVENLABS_API_KEY` | voce cloud (STT Scribe + TTS); se assente → Whisper + Piper |
| `ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL` | voce (default George / turbo_v2_5) |
| `DANTE_WEB_USER` / `DANTE_WEB_PASSWORD` | Basic Auth della UI (obbligatoria) |
| `DANTE_MOOD=1` | riattiva la lettura prosodica dell'umore (soglie da tarare) |

## Sicurezza (Fase 1 = sola lettura)
- Gate `agent/permissions.py`: consente solo i tool `mcp__neoflux-*` + `ToolSearch`, nega il resto.
- I server MCP espongono solo endpoint/comandi **fissi di lettura**, input validati.
- Segreti in `config/*.yaml` e `.env` (gitignored). UI protetta da Basic Auth + HTTPS.

Dettagli architettura, struttura e roadmap: **[CLAUDE.md](./CLAUDE.md)** · deploy: **[DEPLOY.md](./DEPLOY.md)**.
