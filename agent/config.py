"""Configurazione dell'agente DANTE (opzioni Claude Agent SDK)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from .hooks import audit_post_tool_use
from .permissions import gate_pretooluse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = sys.executable  # il python del venv, con mcp/paramiko/pyyaml installati


def _load_dotenv() -> None:
    """Carica le variabili da un file .env alla radice del progetto (es. ANTHROPIC_API_KEY).
    Loader minimale senza dipendenze; non sovrascrive variabili già presenti nell'ambiente."""
    envf = PROJECT_ROOT / ".env"
    if not envf.exists():
        return
    for line in envf.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

SYSTEM_PROMPT = """\
Sei DANTE, l'assistente operativo dell'azienda Neoflux (hosting e gestione server).

RUOLO
- Aiuti il team a capire lo stato dell'infrastruttura: server Linux, VM Proxmox,
  hosting cPanel/Plesk.
- FASE ATTUALE: sola lettura ("Osservatore"). Puoi diagnosticare e riferire, ma
  NON puoi modificare nulla. Se serve un'azione di scrittura, spiega cosa faresti
  e di' che richiederà l'approvazione umana prevista in Fase 2.

STILE
- Rispondi in italiano, in modo conciso e operativo, come un buon sysadmin.
- Prima i fatti concreti (numeri, stati), poi eventuali raccomandazioni.
- Quando riscontri un problema (disco quasi pieno, servizio failed, load alto),
  segnalalo chiaramente e proponi il prossimo passo diagnostico.

STRUMENTI
- mcp__neoflux-ssh__* : host Linux via SSH (list_hosts, host_overview, disk_usage,
  memory_usage, service_status, failed_services, tail_log). Usali per le VPS
  esterne e i server raggiungibili via SSH. Parti da list_hosts e host_overview.
- mcp__neoflux-virtualizor__* : piattaforma Virtualizor via Admin API (vz_list_servers
  per i nodi, vz_list_vps per le VPS, vz_vps_info/vz_vps_stats per i dettagli,
  vz_server_loads per i carichi). Usali per la panoramica delle VPS gestite su Virtualizor.
- Scegli lo strumento giusto in base alla domanda; per un problema su una VPS di
  Virtualizor combina vz_vps_stats (metriche) e, se hai accesso SSH a quella VPS,
  gli strumenti ssh per i dettagli interni.
- Non inventare mai valori: se non hai eseguito lo strumento, dillo.
"""


def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={
            "neoflux-ssh": {
                "type": "stdio",
                "command": VENV_PYTHON,
                "args": ["-m", "mcp_servers.ssh_read"],
                "env": {"PYTHONPATH": str(PROJECT_ROOT)},
            },
            "neoflux-virtualizor": {
                "type": "stdio",
                "command": VENV_PYTHON,
                "args": ["-m", "mcp_servers.virtualizor_read"],
                "env": {"PYTHONPATH": str(PROJECT_ROOT)},
            },
        },
        # Difesa in profondità: gli strumenti pericolosi sono comunque hard-bloccati,
        # a prescindere dal gate. Il gate PreToolUse resta la fonte di verità.
        disallowed_tools=[
            "Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch",
        ],
        permission_mode="default",
        # Gate autoritativo (allow/deny per OGNI tool) + audit delle esecuzioni.
        hooks={
            "PreToolUse": [HookMatcher(matcher=None, hooks=[gate_pretooluse])],
            "PostToolUse": [HookMatcher(matcher=None, hooks=[audit_post_tool_use])],
        },
        cwd=str(PROJECT_ROOT),
        # Non ereditare i settings globali dell'utente: DANTE è isolato e riproducibile.
        setting_sources=None,
    )
