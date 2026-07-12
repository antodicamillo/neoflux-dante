"""Helper per il pannello /admin di DANTE: gestione connessioni (Virtualizor, Webuzo,
host SSH) scritte nei file config/*.yaml che gli MCP server leggono. Funzioni pure
(niente FastAPI): il routing sta in server.py, che riusa l'autenticazione.

Sicurezza: i segreti stanno nei file gitignored (chmod 600). Il pannello è protetto
dalla stessa Basic Auth dell'app. Solo LETTURA lato infrastruttura (test = una lettura).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml

_CONF = Path(__file__).resolve().parent.parent / "config"

# tipo → (file, chiave-collezione, campi con default)
TYPES: dict[str, dict[str, Any]] = {
    "virtualizor": {
        "file": "virtualizor.yaml", "coll": "masters",
        "fields": {"host": "", "port": 4085, "apikey": "", "apipass": "",
                   "admin_auth": True, "verify_ssl": False, "description": ""},
    },
    "webuzo": {
        "file": "webuzo.yaml", "coll": "servers",
        "fields": {"host": "", "port": 2005, "apiuser": "root", "apikey": "",
                   "verify_ssl": False, "description": ""},
    },
    "ssh": {
        "file": "inventory.yaml", "coll": "hosts",
        "fields": {"hostname": "", "port": 22, "username": "root",
                   "key_filename": "", "password": "", "description": ""},
    },
}
_SECRET_FIELDS = {"apikey", "apipass", "password"}


def _path(t: str) -> Path:
    return _CONF / TYPES[t]["file"]


def load(t: str) -> dict:
    p = _path(t)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    coll = data.get(TYPES[t]["coll"])
    return coll if isinstance(coll, dict) else {}


def save(t: str, coll: dict) -> None:
    p = _path(t)
    p.write_text(yaml.safe_dump({TYPES[t]["coll"]: coll}, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def masked(coll: dict) -> dict:
    """Entry con i segreti mascherati (per mostrarle nel pannello)."""
    out = {}
    for name, e in coll.items():
        out[name] = {k: ("••••••" if k in _SECRET_FIELDS and v else v) for k, v in e.items()}
    return out


def clean_config(t: str, cfg: dict) -> dict:
    """Tiene solo i campi previsti per il tipo, con i tipi giusti; scarta segreti vuoti."""
    fields = TYPES[t]["fields"]
    out: dict[str, Any] = {}
    for k, default in fields.items():
        v = cfg.get(k, default)
        if isinstance(default, bool):
            v = str(v).lower() in ("true", "1", "yes", "on") if not isinstance(v, bool) else v
        elif isinstance(default, int) and not isinstance(v, bool):
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = default
        if k in _SECRET_FIELDS and (v is None or v == ""):
            continue  # non sovrascrivere/svuotare i segreti
        out[k] = v
    return out


# --- test di connessione (una LETTURA) --------------------------------------

def _test_virtualizor(c: dict) -> str:
    url = f"https://{c['host']}:{c.get('port', 4085)}/index.php"
    r = httpx.get(url, params={"act": "servers", "api": "json",
                               "adminapikey": c["apikey"], "adminapipass": c["apipass"]},
                  verify=False, timeout=15, follow_redirects=True)
    r.raise_for_status()
    d = r.json()
    if d.get("fatal_error_text"):
        raise ValueError(d["fatal_error_text"])
    servers = d.get("servers") or d.get("servs") or []
    n = len(servers) if isinstance(servers, (list, dict)) else 0
    return f"OK — {n} nodo/i, connessione valida"


def _test_webuzo(c: dict) -> str:
    url = f"https://{c['host']}:{c.get('port', 2005)}/index.php"
    r = httpx.post(url, params={"act": "users", "api": "json"},
                   data={"apiuser": c.get("apiuser", "root"), "apikey": c["apikey"]},
                   verify=False, timeout=15, follow_redirects=True)
    r.raise_for_status()
    d = r.json()
    if d.get("fatal_error_text") or d.get("error"):
        raise ValueError(str(d.get("fatal_error_text") or d.get("error")))
    return f"OK — {len(d.get('users') or {})} account, connessione valida"


def _test_ssh(c: dict) -> str:
    import paramiko
    cl = paramiko.SSHClient()
    cl.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = {"hostname": c["hostname"], "port": int(c.get("port", 22)),
          "username": c.get("username", "root"), "timeout": 10,
          "banner_timeout": 10, "auth_timeout": 10}
    if c.get("key_filename"):
        kw["key_filename"] = str(Path(c["key_filename"]).expanduser())
    if c.get("password"):
        kw["password"] = c["password"]
    try:
        cl.connect(**kw)
        _in, out, _err = cl.exec_command("uptime", timeout=10)
        res = out.read().decode("utf-8", "replace").strip()[:70]
    finally:
        cl.close()
    return f"OK — {res or 'connesso'}"


_TESTERS = {"virtualizor": _test_virtualizor, "webuzo": _test_webuzo, "ssh": _test_ssh}


def test(t: str, cfg: dict) -> str:
    """Prova la connessione; ritorna un messaggio OK o solleva un'eccezione."""
    return _TESTERS[t](cfg)
