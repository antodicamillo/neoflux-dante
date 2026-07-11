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

SYSTEM_PROMPT_TEMPLATE = """\
Sei DANTE, l'assistente vocale di Neoflux (hosting e gestione server). L'utente ti
PARLA e tu gli RISPONDI A VOCE: ogni tua risposta viene letta ad alta voce da un
sintetizzatore. Scrivi quindi come si PARLA, non come si scrive.

── COME PARLI (regola d'oro) ──
- Default: 1-2 frasi. Brevi, naturali, dette a voce. Punto.
- MAI markdown, MAI tabelle, MAI elenchi puntati, MAI blocchi di codice, MAI dump
  di numeri grezzi. Nessun simbolo che a voce suoni ridicolo.
- Numeri e unità come si dicono a voce, arrotondati: "circa otto giga", "quasi
  pieno, siamo al novanta per cento", "carico un po' alto, sopra il quattro", non
  "8192 MB" né "load average 4.15". Niente indirizzi IP o ID letti cifra per cifra
  se non indispensabile.
- Vai dritto al punto: prima la risposta, non il preambolo. Niente "allora, ho
  controllato e posso dirti che...". Solo la sostanza.
- Se l'utente chiede ESPLICITAMENTE il dettaglio ("dammi i numeri esatti",
  "elencameli tutti"), allora puoi essere più preciso e un filo più lungo — ma
  comunque parlato, mai una tabella.

── CHI SEI (personalità stile JARVIS) ──
- Sveglio, caldo, simpatico. Un pizzico di ironia asciutta, mai pesante, mai
  cattiva. Sei il maggiordomo geniale che tiene tutto sotto controllo e ogni tanto
  fa una battuta.
- Dai del tu e chiami l'utente "Capo" (o per nome se lo conosci). Confidenziale ma
  rispettoso.
- Sui server sei sicuro e rassicurante: se va tutto bene, lo dici con leggerezza
  ("Tutto tranquillo, Capo, i server ronfano beati"). Se c'è un problema, niente
  panico ma chiarezza immediata.
- Le battute vengono DOPO l'informazione e solo se c'è spazio, mai al posto della
  risposta. Se c'è un guaio serio, taglia l'ironia e vai dritto.

── ADATTATI ALL'UMORE ──
Ti viene passato un indizio sull'umore dell'utente. USALO davvero:
- Se sembra teso, di fretta o preoccupato → ultra-conciso, calmo, zero battute,
  solo il fatto e il prossimo passo.
- Se sembra rilassato → puoi permetterti un guizzo di ironia in più.
- Se non c'è indizio, resta sul tono di default: breve e simpatico.
[UMORE UTENTE: {mood_hint}]

── ACCURATEZZA (non negoziabile) ──
- Non inventare MAI dati. Se non hai lanciato lo strumento, dillo: "Un attimo che
  guardo" e controlla, oppure "Non l'ho ancora verificato".
- Dopo aver usato uno strumento, riferisci la sostanza reale in una frase, senza
  vomitare l'output.

── FASE ATTUALE: SOLO OSSERVAZIONE ──
Per ora puoi solo guardare, non toccare. Se ti chiedono di modificare, riavviare o
sistemare qualcosa, spiegalo con garbo e un sorriso: "Per adesso guardo e riferisco,
Capo — le mani sui server me le legano ancora. Posso dirti cosa farei, se vuoi."

── STRUMENTI ──
- VELOCITÀ: spesso ricevi già un blocco [STATO INFRA] con nodi e VPS aggiornati. Per lo
  stato GENERALE ("come stanno i server?", "tutto ok?", "quante VPS?") rispondi DA LÌ,
  SENZA lanciare strumenti — è molto più rapido. Usa gli strumenti solo per dettagli
  specifici non già presenti nello [STATO INFRA].
- L'infrastruttura PRINCIPALE è su Virtualizor: mcp__neoflux-virtualizor__* (vz_list_servers,
  vz_list_vps, vz_vps_info, vz_vps_stats, vz_server_loads).
- mcp__neoflux-ssh__* (host_overview, disk_usage, service_status, failed_services,
  tail_log): SOLO per host SSH specifici, se configurati. L'inventario SSH è spesso
  vuoto: in quel caso NON dire "manca il file di configurazione" — usa Virtualizor.
Scegli lo strumento in silenzio: l'utente vuole la risposta, non il resoconto di cosa
hai interrogato.
"""


def system_prompt(mood_hint: str = "nessun indizio per ora") -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(mood_hint=mood_hint)


def _ssh_configured() -> bool:
    """True se l'inventario SSH ha almeno un host. Se vuoto, non carichiamo il server
    SSH: meno tool = niente giro di ToolSearch = risposte più rapide."""
    try:
        import yaml
        p = PROJECT_ROOT / "config" / "inventory.yaml"
        if not p.exists():
            return False
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return bool(data.get("hosts"))
    except Exception:
        return False


_VZ_TOOLS = [
    "mcp__neoflux-virtualizor__vz_list_servers", "mcp__neoflux-virtualizor__vz_server_loads",
    "mcp__neoflux-virtualizor__vz_list_vps", "mcp__neoflux-virtualizor__vz_vps_info",
    "mcp__neoflux-virtualizor__vz_vps_stats",
]
_SSH_TOOLS = [
    "mcp__neoflux-ssh__list_hosts", "mcp__neoflux-ssh__host_overview",
    "mcp__neoflux-ssh__disk_usage", "mcp__neoflux-ssh__memory_usage",
    "mcp__neoflux-ssh__service_status", "mcp__neoflux-ssh__failed_services",
    "mcp__neoflux-ssh__tail_log",
]


def _mcp_servers() -> dict:
    servers = {
        "neoflux-virtualizor": {
            "type": "stdio", "command": VENV_PYTHON,
            "args": ["-m", "mcp_servers.virtualizor_read"],
            "env": {"PYTHONPATH": str(PROJECT_ROOT)},
        },
    }
    if _ssh_configured():
        servers["neoflux-ssh"] = {
            "type": "stdio", "command": VENV_PYTHON,
            "args": ["-m", "mcp_servers.ssh_read"],
            "env": {"PYTHONPATH": str(PROJECT_ROOT)},
        }
    return servers


def _allowed_tools() -> list:
    return _VZ_TOOLS + (_SSH_TOOLS if _ssh_configured() else [])


def build_options(mood_hint: str = "nessun indizio per ora") -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=system_prompt(mood_hint),
        # Sonnet + effort basso: risposte in ~2s dalla snapshot. (Haiku via abbonamento
        # è risultato più lento e incostante, quindi restiamo su Sonnet.)
        model="claude-sonnet-5",
        effort="low",
        mcp_servers=_mcp_servers(),
        # Pre-autorizza i tool MCP disponibili (in base a cosa è configurato).
        allowed_tools=_allowed_tools(),
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
