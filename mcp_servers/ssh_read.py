"""Neoflux DANTE — SSH read-only MCP server.

Exposes a small set of *read-only* diagnostic tools over SSH. Every tool runs a
FIXED command template; the only user-controlled parts (host, service name, log
path, line count) are strictly validated and shell-quoted. There is intentionally
NO "run arbitrary command" tool here — that belongs to a future, approval-gated
write server, never to the read-only surface.

Run standalone (stdio) so it is reusable by the Agent SDK, the Claude Code CLI,
and CI:

    python -m mcp_servers.ssh_read
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import paramiko
import yaml
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("neoflux-ssh")

# --- Inventory -------------------------------------------------------------

_INVENTORY_PATH = Path(__file__).resolve().parent.parent / "config" / "inventory.yaml"
_EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config" / "inventory.example.yaml"


def _load_inventory() -> dict:
    path = _INVENTORY_PATH if _INVENTORY_PATH.exists() else _EXAMPLE_PATH
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("hosts", {})


# --- Validation ------------------------------------------------------------

_SERVICE_RE = re.compile(r"^[A-Za-z0-9@._-]{1,128}$")
_ALLOWED_LOG_DIRS = ("/var/log/",)


def _require_host(host: str) -> dict:
    hosts = _load_inventory()
    if host not in hosts:
        known = ", ".join(sorted(hosts)) or "(nessuno configurato)"
        raise ValueError(f"Host '{host}' non in inventario. Host noti: {known}")
    return hosts[host]


# --- SSH transport ---------------------------------------------------------

def _run_ssh(host: str, command: str, timeout: int = 15) -> str:
    """Open a short-lived SSH connection, run one command, return stdout+stderr."""
    cfg = _require_host(host)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # Trusted, single-operator context. For hardening, switch to RejectPolicy
    # and manage known_hosts explicitly.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": cfg["hostname"],
        "port": int(cfg.get("port", 22)),
        "username": cfg.get("username", "root"),
        "timeout": timeout,
        "banner_timeout": timeout,
        "auth_timeout": timeout,
    }
    if cfg.get("key_filename"):
        connect_kwargs["key_filename"] = str(Path(cfg["key_filename"]).expanduser())
    if cfg.get("password"):
        connect_kwargs["password"] = cfg["password"]

    try:
        client.connect(**connect_kwargs)
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
    finally:
        client.close()

    result = out.strip()
    if err.strip():
        result += f"\n[stderr] {err.strip()}"
    return result or "(nessun output)"


# --- Tools (all read-only) -------------------------------------------------

@mcp.tool()
def list_hosts() -> str:
    """Elenca gli host gestiti definiti nell'inventario di Neoflux."""
    hosts = _load_inventory()
    if not hosts:
        return "Nessun host in inventario. Crea config/inventory.yaml da inventory.example.yaml."
    lines = [
        f"- {name}: {cfg.get('username','root')}@{cfg.get('hostname')}:{cfg.get('port',22)}"
        f"  ({cfg.get('description','')})".rstrip()
        for name, cfg in hosts.items()
    ]
    return "Host gestiti:\n" + "\n".join(lines)


@mcp.tool()
def host_overview(host: str) -> str:
    """Panoramica rapida di un host: uptime, carico, memoria e uso disco."""
    cmd = (
        "echo '### uptime' && uptime && "
        "echo '### memoria' && free -h && "
        "echo '### disco' && df -h -x tmpfs -x devtmpfs && "
        "echo '### top processi' && ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -6"
    )
    return _run_ssh(host, cmd)


@mcp.tool()
def disk_usage(host: str) -> str:
    """Uso del disco (df -h) su un host, esclusi i filesystem temporanei."""
    return _run_ssh(host, "df -h -x tmpfs -x devtmpfs")


@mcp.tool()
def memory_usage(host: str) -> str:
    """Uso di memoria e swap (free -h) su un host."""
    return _run_ssh(host, "free -h")


@mcp.tool()
def service_status(host: str, service: str) -> str:
    """Stato di un servizio systemd (systemctl status, read-only) su un host."""
    if not _SERVICE_RE.match(service):
        raise ValueError(f"Nome servizio non valido: {service!r}")
    cmd = f"systemctl status {shlex.quote(service)} --no-pager -l | head -30"
    return _run_ssh(host, cmd)


@mcp.tool()
def failed_services(host: str) -> str:
    """Elenca le unità systemd in stato failed su un host."""
    return _run_ssh(host, "systemctl --failed --no-pager -l")


@mcp.tool()
def tail_log(host: str, path: str, lines: int = 100) -> str:
    """Ultime righe di un file di log. Consentito solo sotto /var/log/."""
    if not path.startswith(_ALLOWED_LOG_DIRS):
        raise ValueError(f"Percorso non consentito: {path!r}. Consentito solo /var/log/.")
    if ".." in path:
        raise ValueError("Path traversal non consentito.")
    n = max(1, min(int(lines), 500))
    cmd = f"tail -n {n} {shlex.quote(path)}"
    return _run_ssh(host, cmd)


if __name__ == "__main__":
    mcp.run()
