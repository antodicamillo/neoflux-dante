"""Neoflux DANTE — Webuzo Admin API, MCP server READ-ONLY.

Webuzo (Softaculous, come Virtualizor) — pannello single-server. Interroga l'Admin
API solo in lettura: account, uso risorse per account, domini, banda. Nessuna azione
di scrittura è esposta: la whitelist di `act=` contiene solo endpoint di lettura.

Differenze da Virtualizor: porta 2005 (admin HTTPS), auth `apiuser`+`apikey` (POST) o
HTTP Basic (root:password), `api=json` obbligatorio, cert self-signed.

Credenziali in config/webuzo.yaml (gitignored). Avvio standalone:
    python -m mcp_servers.webuzo_read
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import yaml
from mcp.server.fastmcp import FastMCP

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

mcp = FastMCP("neoflux-webuzo")

_CONF_PATH = Path(__file__).resolve().parent.parent / "config" / "webuzo.yaml"
_EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config" / "webuzo.example.yaml"

# SOLO endpoint di lettura (Webuzo è action-based, senza flag read/write → allowlist rigida).
_READ_ACTIONS = {"users", "domains", "bandwidth", "ips", "storage"}


def _servers() -> dict:
    """Ritorna il dict dei server Webuzo. Supporta il formato multi 'servers: {nome: {...}}'
    e, per retrocompatibilità, una singola config flat (host in cima)."""
    path = _CONF_PATH if _CONF_PATH.exists() else _EXAMPLE_PATH
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data.get("servers"), dict):
        return data["servers"]
    if data.get("host"):                       # config flat legacy → un solo server
        return {"webuzo": data}
    return {}


def _call(cfg: dict, act: str, params: dict[str, Any] | None = None) -> dict:
    if act not in _READ_ACTIONS:
        raise ValueError(f"Azione '{act}' non consentita (solo lettura).")
    if not cfg.get("host"):
        raise ValueError("Webuzo non configurato.")
    url = f"https://{cfg['host']}:{cfg.get('port', 2005)}/index.php"
    query = {"api": "json", "act": act, **{k: v for k, v in (params or {}).items() if v is not None}}
    data, auth = None, None
    if cfg.get("apikey"):
        data = {"apiuser": cfg.get("apiuser", "root"), "apikey": cfg["apikey"]}
    elif cfg.get("password"):
        auth = (cfg.get("apiuser", "root"), cfg["password"])
    resp = httpx.post(
        url, params=query, data=data, auth=auth,
        verify=bool(cfg.get("verify_ssl", False)), timeout=30, follow_redirects=True,
    )
    resp.raise_for_status()
    try:
        j = resp.json()
    except Exception as exc:
        raise ValueError(f"Risposta non-JSON da Webuzo (manca api=json o auth?): {exc}") from exc
    # Webuzo mette gli errori in 'error' o 'fatal_error_text'
    if isinstance(j, dict) and (j.get("fatal_error_text") or j.get("error")):
        raise ValueError(str(j.get("fatal_error_text") or j.get("error")))
    return j


# --- helper formattazione ---------------------------------------------------

def _res(user: dict, key: str) -> str:
    """Estrae 'used/limit (percent%)' dal blocco resource di un account."""
    r = (user.get("resource") or {}).get(key) or {}
    used, lim, pct = r.get("used", "?"), r.get("limit", "?"), r.get("percent")
    s = f"{used}/{lim}"
    if pct not in (None, "", "?"):
        s += f" ({pct}%)"
    return s


# --- tool (tutti read-only) -------------------------------------------------

@mcp.tool()
def wz_list_users() -> str:
    """Elenca gli account Webuzo (per ogni server) con uso di disco, banda, email, database."""
    servers = _servers()
    if not servers:
        return "Nessun server Webuzo configurato."
    out = []
    for sname, cfg in servers.items():
        try:
            users = _call(cfg, "users").get("users") or {}
            out.append(f"[{sname}] account ({len(users)}):")
            for name, u in users.items():
                out.append(
                    f"- {name} ({u.get('domain','?')}) stato={u.get('status','?')} "
                    f"disco {_res(u,'disk')} GB · banda {_res(u,'bandwidth')} · "
                    f"email {_res(u,'email_account')} · db {_res(u,'db')}"
                )
        except Exception as e:
            out.append(f"[{sname}] errore: {e}")
    return "\n".join(out)


@mcp.tool()
def wz_account(user: str) -> str:
    """Dettagli di un singolo account Webuzo (cerca su tutti i server): risorse, dominio, home."""
    for sname, cfg in _servers().items():
        try:
            u = (_call(cfg, "users").get("users") or {}).get(user)
        except Exception:
            u = None
        if u:
            return (
                f"[{sname}] Account {user} — dominio {u.get('domain','?')}, stato "
                f"{u.get('status','?')}, piano {u.get('plan','?')}\n"
                f"- disco: {_res(u,'disk')} GB\n"
                f"- banda: {_res(u,'bandwidth')}\n"
                f"- email: {_res(u,'email_account')} · database: {_res(u,'db')}\n"
                f"- domini addon: {_res(u,'addondom')} · sottodomini: {_res(u,'subdom')}\n"
                f"- home: {u.get('homedir','?')} · IP: {u.get('ip','?')}"
            )
    return f"Account '{user}' non trovato su nessun server Webuzo."


@mcp.tool()
def wz_list_domains() -> str:
    """Elenca i domini gestiti da Webuzo (per ogni server): utente, tipo, versione PHP, IP."""
    servers = _servers()
    if not servers:
        return "Nessun server Webuzo configurato."
    out = []
    for sname, cfg in servers.items():
        try:
            doms = _call(cfg, "domains", {"reslen": "all"}).get("domains") or {}
            out.append(f"[{sname}] domini ({len(doms)}):")
            for _id, d in doms.items():
                out.append(
                    f"- {d.get('domain','?')} (utente {d.get('user','?')}) "
                    f"tipo={d.get('type','?')} php={d.get('php_version','?')} ip={d.get('ip','?')}"
                )
        except Exception as e:
            out.append(f"[{sname}] errore: {e}")
    return "\n".join(out)


if __name__ == "__main__":
    mcp.run()
