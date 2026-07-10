"""Neoflux DANTE — Virtualizor Admin API, MCP server READ-ONLY.

Interroga l'Admin API di Virtualizor (Softaculous) solo in lettura: elenco nodi,
VPS, carichi e statistiche live. Nessuna azione di start/stop/create/delete è
esposta: la whitelist di `act=` contiene esclusivamente endpoint di lettura.

Auth (Scheme A, plaintext su HTTPS): api=json + apikey + apipass.
Il cert su :4085 è tipicamente self-signed → verify_ssl configurabile (default off).

Credenziali in config/virtualizor.yaml (gitignored). Vedi virtualizor.example.yaml.

Avvio standalone:
    python -m mcp_servers.virtualizor_read
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import yaml
from mcp.server.fastmcp import FastMCP

# IMPORTANTE: httpx logga a livello INFO l'URL completo, che contiene apikey/apipass.
# Alziamo la soglia per non far mai finire i segreti nei log.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

mcp = FastMCP("neoflux-virtualizor")

_CONF_PATH = Path(__file__).resolve().parent.parent / "config" / "virtualizor.yaml"
_EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config" / "virtualizor.example.yaml"

# Whitelist rigida: SOLO endpoint di lettura.
_READ_ACTIONS = {"servers", "serverloads", "vs", "vps_stats", "server_stats", "plans", "users"}


# --- Config ----------------------------------------------------------------

def _load_masters() -> dict:
    path = _CONF_PATH if _CONF_PATH.exists() else _EXAMPLE_PATH
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("masters", {})


def _require_master(master: str | None) -> dict:
    masters = _load_masters()
    if not masters:
        raise ValueError("Nessun master Virtualizor configurato (config/virtualizor.yaml).")
    if master is None:
        master = next(iter(masters))  # primo/unico master
    if master not in masters:
        known = ", ".join(sorted(masters))
        raise ValueError(f"Master '{master}' sconosciuto. Noti: {known}")
    return masters[master]


# --- HTTP ------------------------------------------------------------------

def _call(master: str | None, act: str, params: dict[str, Any]) -> dict:
    if act not in _READ_ACTIONS:
        raise ValueError(f"Azione '{act}' non consentita (solo lettura).")
    cfg = _require_master(master)
    url = f"https://{cfg['host']}:{cfg.get('port', 4085)}/index.php"
    # Su questi install l'Admin API vuole adminapikey/adminapipass (non apikey/apipass).
    # Configurabile via admin_auth: false per gli install che usano lo schema legacy.
    if cfg.get("admin_auth", True):
        auth = {"adminapikey": cfg["apikey"], "adminapipass": cfg["apipass"]}
    else:
        auth = {"apikey": cfg["apikey"], "apipass": cfg["apipass"]}
    query = {
        "act": act,
        "api": "json",
        **auth,
        **{k: v for k, v in params.items() if v is not None},
    }
    resp = httpx.get(
        url,
        params=query,
        verify=bool(cfg.get("verify_ssl", False)),
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception as exc:  # risposta non-JSON (manca api=json? auth fallita?)
        raise ValueError(f"Risposta non-JSON dall'API Virtualizor: {exc}") from exc


def _collection(data: dict, *keys: str) -> dict:
    """Estrae la collezione, provando le chiavi note e poi le chiavi numeriche."""
    for k in keys:
        if isinstance(data.get(k), dict):
            return data[k]
    return {k: v for k, v in data.items() if str(k).isdigit() and isinstance(v, dict)}


# --- Formattatori (puri, testabili) ----------------------------------------

def _ips_str(v: dict) -> str:
    ips = v.get("ips")
    if isinstance(ips, dict):
        return ", ".join(str(x) for x in ips.values())
    if isinstance(ips, list):
        return ", ".join(str(x) for x in ips)
    return str(ips or "")


def _fmt_servers(data: dict) -> str:
    # 'servers' (o 'servs') è una LISTA di nodi su questi install.
    servers = data.get("servers") or data.get("servs")
    if isinstance(servers, dict):
        servers = list(servers.values())
    if not servers:
        return f"Nessun nodo trovato. Chiavi risposta: {list(data)[:8]}"
    lines = ["Nodi Virtualizor:"]
    for s in servers:
        lines.append(
            f"- [{s.get('serid','?')}] {s.get('server_name','?')} ({s.get('ip','?')}) "
            f"virt={s.get('virt','?')}\n"
            f"    RAM disp. {s.get('ram','?')}/{s.get('total_ram','?')} MB · "
            f"disco disp. {s.get('space','?')}/{s.get('total_space','?')} GB · "
            f"{s.get('os','')}".rstrip()
        )
    return "\n".join(lines)


def _fmt_vps_list(data: dict) -> str:
    vps = _collection(data, "vs", "vps")
    if not vps:
        return f"Nessuna VPS trovata. Chiavi risposta: {list(data)[:8]}"
    lines = [f"VPS ({len(vps)}):"]
    for vid, v in vps.items():
        susp = " [SOSPESA]" if str(v.get("suspended", "0")) not in ("0", "", "None") else ""
        lines.append(
            f"- [{vid}] {v.get('vps_name','?')} host={v.get('hostname','?')} "
            f"ip={_ips_str(v)} virt={v.get('virt','?')} "
            f"RAM={v.get('ram','?')}MB cores={v.get('cores','?')}{susp}"
        )
    return "\n".join(lines)


_STATUS_MAP = {"1": "online", "0": "offline", "2": "sospesa"}


def _num(x: Any) -> Any:
    try:
        return round(float(x), 1)
    except (TypeError, ValueError):
        return x


def _fmt_vps_stats(data: dict) -> str:
    vps_data = data.get("vps_data")
    if isinstance(vps_data, dict):
        # può essere keyed by vpsid oppure già il dict di una singola VPS
        inner = next((x for x in vps_data.values() if isinstance(x, dict)), None)
        v = inner if inner is not None else vps_data
    else:
        v = data
    if not isinstance(v, dict) or ("used_ram" not in v and "used_cpu" not in v):
        return f"Statistiche non disponibili. Chiavi risposta: {list(data)[:8]}"
    status = _STATUS_MAP.get(str(v.get("status", "")), str(v.get("status", "?")))
    bw_lim = v.get("bandwidth", "?")
    bw_lim_s = "illimitata" if str(bw_lim) in ("0", "0.0") else f"{_num(bw_lim)} GB"
    return (
        f"VPS {v.get('vps_name', v.get('vpsid','?'))} ({v.get('hostname','?')}) — {status}\n"
        f"- CPU: {_num(v.get('used_cpu','?'))}%\n"
        f"- RAM: {_num(v.get('used_ram','?'))}/{_num(v.get('ram','?'))} MB\n"
        f"- Disco: {_num(v.get('used_disk','?'))}/{_num(v.get('disk','?'))} GB\n"
        f"- Banda usata: {_num(v.get('used_bandwidth','?'))} GB (limite: {bw_lim_s})"
    )


def _fmt_loads(data: dict, top: int = 15) -> str:
    usage = _collection(data, "vpsusage")
    if not usage:
        return f"Nessun dato di carico. Chiavi risposta: {list(data)[:8]}"
    def load15(item):
        try:
            return float(item[1].get("15", 0))
        except Exception:
            return 0.0
    ranked = sorted(usage.items(), key=load15, reverse=True)[:top]
    lines = [f"VPS per carico (load 15m, top {len(ranked)}):"]
    for vid, load in ranked:
        lines.append(f"- [{vid}] load 1/5/15 = "
                     f"{load.get('1','?')}/{load.get('5','?')}/{load.get('15','?')}")
    return "\n".join(lines)


# --- Tools (tutti read-only) -----------------------------------------------

@mcp.tool()
def vz_list_servers(master: str | None = None) -> str:
    """Elenca i nodi (hypervisor) gestiti da un master Virtualizor."""
    return _fmt_servers(_call(master, "servers", {}))


@mcp.tool()
def vz_server_loads(master: str | None = None) -> str:
    """VPS ordinate per carico (load average 1/5/15 minuti)."""
    return _fmt_loads(_call(master, "serverloads", {}))


@mcp.tool()
def vz_list_vps(
    master: str | None = None,
    search: str | None = None,
    status: str | None = None,
    page: int = 1,
) -> str:
    """Elenca le VPS. Filtri opzionali: search (nome/host/ip), status, page."""
    params = {"page": page, "reslen": 50, "search": search, "vsstatus": status}
    return _fmt_vps_list(_call(master, "vs", params))


@mcp.tool()
def vz_vps_info(vpsid: int, master: str | None = None) -> str:
    """Dettagli di una singola VPS per ID."""
    return _fmt_vps_list(_call(master, "vs", {"vpsid": int(vpsid)}))


@mcp.tool()
def vz_vps_stats(vpsid: int, master: str | None = None) -> str:
    """Statistiche live di una VPS: CPU, RAM, disco, banda."""
    return _fmt_vps_stats(_call(master, "vps_stats", {"vpsid": int(vpsid)}))


if __name__ == "__main__":
    mcp.run()
