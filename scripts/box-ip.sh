#!/usr/bin/env bash
# Trova l'IP corrente del box DANTE sulla LAN.
# Il box è in DHCP (nessun IP statico), quindi l'indirizzo può cambiare: questo script
# lo scopre provando gli IP noti e poi, come fallback, scandendo la /24.
# Stampa l'IP su stdout ed esce 0; se non lo trova, esce 1.
set -o pipefail
KEY="${DANTE_SSH_KEY:-$HOME/.ssh/id_rsa}"
SUBNET="${DANTE_SUBNET:-192.168.0}"

_is_box() {  # $1 = ip → 0 se è il box (chiave ssh valida + /opt/neoflux-dante)
  ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new \
    "root@$1" 'test -d /opt/neoflux-dante' 2>/dev/null
}

# 1) IP noti (i più probabili)
for ip in "$SUBNET.201" "$SUBNET.202"; do
  if _is_box "$ip"; then echo "$ip"; exit 0; fi
done

# 2) fallback: prima chi ha la 22 aperta, poi verifica che sia il box
for i in $(seq 1 254); do
  ip="$SUBNET.$i"
  timeout 1 bash -c "exec 3<>/dev/tcp/$ip/22" 2>/dev/null || continue
  if _is_box "$ip"; then echo "$ip"; exit 0; fi
done

exit 1
