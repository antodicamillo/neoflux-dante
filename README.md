# 🛰️ DANTE

**D**on't **A**sk, **N**othing's **T**ruly **E**xploding — l'assistente operativo
AI di **Neoflux**, sullo stile "JARVIS", costruito con **Claude Agent SDK** + **MCP**.

DANTE aiuta a gestire l'infrastruttura Neoflux (Linux, Proxmox, cPanel/Plesk).
È progettato per crescere per **fasi**: oggi è un **Osservatore in sola lettura**,
sicuro da usare da subito; le azioni di scrittura arriveranno dietro approvazione.

## Requisiti
- **Python 3.13** (o ≥ 3.10)
- CLI **`claude`** autenticata (stessa auth di Claude Code — nessuna API key extra)
- Accesso SSH agli host, idealmente con un **utente dedicato di sola lettura**

## Installazione
```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config/inventory.example.yaml config/inventory.yaml
# → compila config/inventory.yaml con i tuoi host SSH

cp config/virtualizor.example.yaml config/virtualizor.yaml
# → inserisci host + apikey/apipass del master Virtualizor
```

## Avvio
```bash
python -m agent.dante
```
Poi chiedi, ad esempio:
- *"Quali host gestiamo?"*
- *"Dammi una panoramica di web-01"*
- *"Ci sono servizi failed su db-01?"*
- *"Mostrami le ultime 50 righe di /var/log/nginx/error.log su web-01"*

## Cosa può fare (Fase 1)
| Strumento | Descrizione |
|-----------|-------------|
| `list_hosts` | Elenca gli host in inventario |
| `host_overview` | Uptime, carico, memoria, disco, top processi |
| `disk_usage` | `df -h` |
| `memory_usage` | `free -h` |
| `service_status` | `systemctl status <servizio>` |
| `failed_services` | Unità systemd in stato failed |
| `tail_log` | Ultime righe di un log sotto `/var/log/` |

**Virtualizor** (Admin API, read-only):

| Strumento | Descrizione |
|-----------|-------------|
| `vz_list_servers` | Elenca i nodi (hypervisor) |
| `vz_list_vps` | Elenca le VPS (filtri: search, status, page) |
| `vz_vps_info` | Dettagli di una VPS |
| `vz_vps_stats` | Metriche live: CPU, RAM, disco, banda |
| `vz_server_loads` | VPS ordinate per carico (load 1/5/15m) |

Tutti **read-only**. DANTE non può modificare nulla in questa fase.

## Sicurezza
- Gate `can_use_tool`: consente solo i tool `mcp__neoflux-*`, nega il resto.
- Tool MCP = comandi fissi di lettura, input validati e shell-quotati.
- Audit completo in `logs/audit.log`.
- Segreti in `config/inventory.yaml` / `.env` (gitignored).

Vedi **[CLAUDE.md](./CLAUDE.md)** per architettura, regole e roadmap complete.
