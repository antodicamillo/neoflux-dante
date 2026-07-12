#!/usr/bin/env bash
# Trova l'IP del box DANTE sulla LAN. Il box è in DHCP (IP instabile), quindi lo
# scopriamo scansionando la /24 per la porta 8800 (servizio DANTE, univoco) in
# PARALLELO (~2-3s). Stampa l'IP su stdout ed esce 0; se non lo trova, esce 1.
# Override: DANTE_SUBNET (default 192.168.0), DANTE_PORT (default 8800).
SUBNET="${DANTE_SUBNET:-192.168.0}"
PORT="${DANTE_PORT:-8800}"
# IP statico attuale del box: prova diretta (istantanea) prima dello scan.
STATIC="${DANTE_STATIC_IP:-192.168.0.50}"
if timeout 2 bash -c "exec 3<>/dev/tcp/$STATIC/$PORT" 2>/dev/null; then echo "$STATIC"; exit 0; fi
python3 - "$SUBNET" "$PORT" <<'PY'
import socket, sys, concurrent.futures
sub, port = sys.argv[1], int(sys.argv[2])
def hit(i):
    ip = f"{sub}.{i}"
    s = socket.socket(); s.settimeout(0.6)
    try:
        return ip if s.connect_ex((ip, port)) == 0 else None
    finally:
        s.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=128) as ex:
    for r in ex.map(hit, range(1, 255)):
        if r:
            print(r); sys.exit(0)
sys.exit(1)
PY
