# DANTE — assistente operativo di Neoflux

> **DANTE** = *Don't Ask, Nothing's Truly Exploding*.
> Assistente AI stile "JARVIS" per Neoflux (hosting / gestione server), costruito
> sul **Claude Agent SDK** + **MCP**. Questo file è il contesto persistente:
> leggilo prima di lavorare nel repo.

## Cos'è
Un agente che aiuta il team Neoflux a gestire l'infrastruttura (Linux bare metal,
VM Proxmox, hosting cPanel/Plesk) e — in futuro — a sviluppare software e
auto-correggere bug. Il cervello è Claude via Agent SDK; gli strumenti sono
**server MCP standalone** riutilizzabili anche dalla CLI `claude` e in CI.

## Principio guida: la fiducia si costruisce a fasi
| Fase | Cosa fa DANTE | Stato |
|------|---------------|-------|
| **1 · Osservatore** | Solo lettura: stato server, disco, servizi, log | ← attuale |
| **2 · Assistente** | Azioni di scrittura dietro **approvazione umana** | da fare |
| **3 · Proattivo** | Avvisi e proposte automatiche (cron/eventi) | da fare |
| **4 · Forge/Dev** | Scrive tool e software, si auto-corregge via CI/PR | da fare |

## Architettura
```
Tu (REPL / futura UI Electron)
      │
  agent/dante.py  ── Claude Agent SDK (loop, memoria, permessi)
      │  parla MCP
  mcp_servers/ssh_read.py   (stdio, SOLO LETTURA)
      │  SSH read-only
  Host Neoflux (da config/inventory.yaml)
```

## Regole di sicurezza (NON derogare)
- **Fase 1 è read-only.** Il gate `agent/permissions.py` consente SOLO i tool
  `mcp__neoflux-*` e nega tutto il resto (Bash locale, Write, Edit, web…).
- I server MCP espongono **solo comandi fissi di lettura**. Vietato aggiungere un
  tool "esegui comando arbitrario" alla superficie read-only.
- Ogni input variabile (host, servizio, path) va **validato e shell-quotato**.
- Ogni decisione ed esecuzione finisce in `logs/audit.log` (append-only).
- I segreti stanno in `config/inventory.yaml` e `.env` (gitignored). Mai committarli.
- Le azioni di scrittura, quando arriveranno (Fase 2), passeranno da
  `can_use_tool` come **richiesta di approvazione**, non da auto-esecuzione.

## Struttura del repo
```
agent/
  dante.py        # REPL interattivo (entry point)
  config.py       # ClaudeAgentOptions (prompt, mcp_servers, tool consentiti)
  permissions.py  # gate can_use_tool (read-only in Fase 1)
  hooks.py        # PostToolUse → audit
  audit.py        # logger append-only
mcp_servers/
  ssh_read.py           # server MCP stdio: tool SSH di sola lettura
  virtualizor_read.py   # server MCP stdio: Virtualizor Admin API (read-only)
config/
  inventory.example.yaml      # modello host SSH (copia in inventory.yaml)
  virtualizor.example.yaml    # modello master Virtualizor (copia in virtualizor.yaml)
logs/audit.log    # audit (gitignored)
```

## Come si esegue
```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/inventory.example.yaml config/inventory.yaml   # e compila gli host
python -m agent.dante
```
Auth: usa la CLI `claude` già autenticata (stessa auth di Claude Code); non serve
una API key separata.

## Aggiungere un nuovo server MCP (pattern)
1. Nuovo file in `mcp_servers/` con `FastMCP("neoflux-<nome>")` e `@mcp.tool()`
   **solo per letture**, input validati.
2. Registra il server in `agent/config.py` (`mcp_servers` + `allowed_tools`).
3. Il prefisso `mcp__neoflux-` fa sì che il gate lo consideri read-only-safe.

## Prossimi passi previsti
- ~~MCP `neoflux-virtualizor`~~ ✅ fatto (Admin API read-only: nodi, VPS, carichi, stats).
- MCP `neoflux-cpanel` (read: domini, DB, code mail).
- Memoria di sessione persistente + inventario auto-appreso.
- UI stile `ada_v2` (Electron + React + Three.js + voce) come guscio.
- Traccia Dev: `claude-code-action` in CI per fix automatici via PR.
