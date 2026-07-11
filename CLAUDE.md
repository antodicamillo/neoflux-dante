# DANTE — assistente vocale operativo di Neoflux

> **DANTE** = *Don't Ask, Nothing's Truly Exploding*.
> Assistente AI stile "JARVIS" per Neoflux (hosting / gestione server), costruito
> sul **Claude Agent SDK** + **MCP**, con UI web vocale. Questo file è il contesto
> persistente: leggilo prima di lavorare nel repo.

## Cos'è
Ci **parli a voce** e ti risponde a voce: osserva l'infrastruttura Neoflux
(Virtualizor, server Linux) e riferisce stato/problemi con un carattere spiritoso
("Capo"). Il cervello è Claude via Agent SDK; gli strumenti sono **server MCP
standalone** read-only, riutilizzabili anche dalla CLI `claude` e in CI.

## Principio guida: la fiducia si costruisce a fasi
| Fase | Cosa fa DANTE | Stato |
|------|---------------|-------|
| **1 · Osservatore** | Solo lettura: stato server/VPS, carichi, alert | ← attuale |
| **2 · Assistente** | Azioni di scrittura dietro **approvazione umana** | da fare |
| **3 · Proattivo** | Avvisi automatici (cron/eventi, Telegram/email) | da fare |
| **4 · Forge/Dev** | Scrive tool e software, si auto-corregge via CI/PR | da fare |

## Architettura (attuale)
```
Browser — UI voce-first (web/static/index.html: orb 3D Three.js, boot, stati)
   │  HTTPS (cert self-signed) + WebSocket
web/server.py  (FastAPI, servizio systemd `dante-web`, Basic Auth)
   ├─ /ws   → ClaudeSDKClient (Sonnet, effort low) + SNAPSHOT infra iniettata a ogni
   │          turno → per lo stato generale risponde SENZA tool in ~2-4s
   ├─ /stt  → ElevenLabs Scribe (ripiego locale: faster-whisper)
   ├─ /tts  → ElevenLabs turbo, voce "George" (ripiego locale: Piper it_IT)
   └─ snapshot poller: Virtualizor ogni 30s → nodo + VPS live + riga alert (soglie)
        │  parla MCP (solo tool read-only)
   mcp_servers/virtualizor_read.py · ssh_read.py   (stdio, SOLA LETTURA)
        │
   Virtualizor Admin API (adminapikey) · host SSH (config/*.yaml)
```
- Gira sul **ProLiant** (Ubuntu, utente `dante`, `/opt/neoflux-dante`), HTTPS su :8800.
- Circuit breaker: se ElevenLabs fallisce (429/quota), 5 min di cooldown → motori locali.
- Esiste ancora il REPL `agent/dante.py` per test locali da terminale.

## Regole di sicurezza (NON derogare)
- **Fase 1 è read-only.** Il gate `agent/permissions.py` (hook PreToolUse) consente SOLO
  i tool `mcp__neoflux-*` + `ToolSearch` e nega tutto il resto (Bash, Write, Edit, web…).
- I server MCP espongono **solo comandi/endpoint fissi di lettura**. Vietato un tool
  "esegui comando arbitrario" sulla superficie read-only.
- Ogni input variabile (host, servizio, path, vpsid) va **validato**.
- Segreti in `config/*.yaml` e `.env` (gitignored, sul box). Mai committarli.
- Le azioni di scrittura (Fase 2) passeranno dal gate come **richiesta di approvazione**.

## Struttura del repo
```
agent/
  dante.py        # REPL interattivo (test locale)
  config.py       # ClaudeAgentOptions: prompt/persona, model, mcp_servers, gate; snapshot-aware
  permissions.py  # gate PreToolUse (read-only)
  hooks.py        # PostToolUse → audit
  audit.py        # logger append-only
  prosody.py      # umore dalla voce (OFF di default: DANTE_MOOD=1 dopo calibrazione)
web/
  server.py       # FastAPI: /ws /stt /tts /health + snapshot poller + circuit breaker
  static/index.html  # UI voce-first (orb, boot, icone SVG, riconnessione WS)
  static/vendor/  # three.min.js + font (vendored, offline-safe)
mcp_servers/
  virtualizor_read.py   # Virtualizor Admin API (read-only)
  ssh_read.py           # host SSH (read-only)
tests/            # pytest: gate, formattatori vz, config
config/
  *.example.yaml  # modelli (copia in inventory.yaml / virtualizor.yaml, gitignored)
NIGHT_LOG.md      # registro dello sviluppo autonomo notturno
DEPLOY.md         # deploy sul box
```

## Come si esegue
**Sul box (produzione):** servizio `dante-web` → `https://<box>:8800` (Basic Auth).
Config in `web/server.py`; env in `/opt/neoflux-dante/.env` (OAuth token, ELEVENLABS_API_KEY,
DANTE_WEB_*). Riavvio: `systemctl restart dante-web`.

**Test locale (REPL):**
```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/virtualizor.example.yaml config/virtualizor.yaml   # + credenziali
python -m agent.dante
```
Auth cervello: CLI `claude` autenticata, oppure `CLAUDE_CODE_OAUTH_TOKEN` (headless).

## Motori voce (configurabili via env)
- `ELEVENLABS_API_KEY` presente → STT Scribe + TTS ElevenLabs. Altrimenti Whisper + Piper.
- `ELEVENLABS_VOICE_ID` (default George), `ELEVENLABS_MODEL` (default eleven_turbo_v2_5).
- `DANTE_MOOD=1` riattiva la lettura prosodica dell'umore (soglie da tarare).

## Aggiungere un nuovo server MCP (pattern)
1. Nuovo file in `mcp_servers/` con `FastMCP("neoflux-<nome>")` e `@mcp.tool()` **solo
   letture**, input validati.
2. Registralo in `agent/config.py` (`_mcp_servers()` + `_allowed_tools()`).
3. Il prefisso `mcp__neoflux-` lo rende read-only-safe per il gate.

## Test
`./.venv/bin/python -m pytest tests/ -q` (gate, formattatori, config).

## Prossimi passi previsti
- MCP `neoflux-cpanel` (read: domini, DB, code mail).
- Fase 2: azioni con approvazione umana.
- Fase 3: proattivo (alert Telegram/email) + accesso remoto (WireGuard).
- Eventuale real-time speech-to-speech (ElevenLabs Conversational AI) per latenza minima.
