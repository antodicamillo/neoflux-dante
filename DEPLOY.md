# Deploy di DANTE sul ProLiant (Proxmox)

Guida per ospitare DANTE su un server **off-site** rispetto all'infrastruttura da
gestire, in un container isolato. Scenario di riferimento: HP ProLiant, Proxmox,
off-site rispetto al master Virtualizor, su UPS con internet stabile.

## 1. Container LXC su Proxmox
Un container LXC basta e avanza (DANTE è leggero: l'AI gira via API).

- Template: **Debian 12** (ha Python 3.11, ok per l'SDK ≥3.10)
- Risorse: **2 vCPU · 4 GB RAM · 20 GB disco** (abbondanti)
- Rete: IP statico sulla LAN; **IP pubblico statico** in uscita (serve per il whitelist)
- Abilita gli **snapshot** Proxmox (rollback rapido)

```bash
# nel container, da root:
apt update && apt -y upgrade
apt -y install python3 python3-venv git curl
# Node + CLI claude (l'Agent SDK la richiede):
curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt -y install nodejs
npm i -g @anthropic-ai/claude-code
```

## 2. Hardening minimo (tiene "le chiavi del regno")
- Utente dedicato non-root per DANTE: `adduser dante`
- SSH **solo a chiave**, niente password, niente root login
- Firewall in uscita/ingresso: DANTE deve poter uscire su 443 (API Anthropic) e
  raggiungere la 4085/22 dell'infra; in ingresso apri solo SSH da IP fidati
- Aggiornamenti automatici di sicurezza (`unattended-upgrades`)

## 3. Porta il codice sul box
**Opzione A — repo git privato (consigliata):** crea un repo privato (GitHub/Gitea),
`git push` da qui, poi sul box `git clone`. Aggiornamenti futuri = `git pull`.

**Opzione B — copia diretta:** dal Mac
```bash
rsync -av --exclude .venv --exclude 'config/*.yaml' --exclude 'logs/*.log' \
  ~/neoflux-dante/ dante@IP_PROLIANT:~/neoflux-dante/
```
> I segreti (`config/*.yaml`) NON viaggiano: li compili sul box.

## 4. Installa
```bash
cd ~/neoflux-dante
./install.sh
```

## 5. Configura
- `config/inventory.yaml` — host SSH (VPS esterne + VPS Neoflux da ispezionare dentro)
- `config/virtualizor.yaml` — master Virtualizor (IP/porta e credenziali stanno
  QUI, non nel repo), `admin_auth: true`, schema `adminapikey`/`adminapipass`
- **Auth headless** (niente browser sul server): usa una API key
  ```bash
  export ANTHROPIC_API_KEY=sk-ant-...      # da console.anthropic.com
  # rendila persistente in /etc/environment o nel systemd unit futuro
  ```

## 6. Connettività verso l'infra (scegli una)
**A — Whitelist IP statico (rapido):** sul server Virtualizor autorizza l'IP pubblico
del ProLiant sulla 4085 (e SSH sulle VPS):
```bash
csf -a <IP_PUBBLICO_PROLIANT> && csf -r
```
Espone la porta solo verso quell'IP. Ok per iniziare, dato che l'IP è statico.

**B — WireGuard (più sicuro, hardening):** tunnel privato tra il ProLiant e un
endpoint nella rete dell'infra → le porte di management non sono mai pubbliche e
DANTE ha un IP VPN statico da whitelistare una volta. Consigliato come passo 2.

## 7. Test
```bash
cd ~/neoflux-dante && source .venv/bin/activate
python -m agent.dante
# "Come sta la piattaforma Virtualizor?"  "Quale VPS consuma più RAM?"
```

## 8. Sempre attivo (più avanti)
Finché DANTE è un REPL interattivo, lo lanci via SSH. Quando aggiungeremo la UI web
o l'heartbeat proattivo (Fase 3), lo trasformiamo in un **servizio systemd** che
parte al boot e resta su. A quel punto: unit file + `ANTHROPIC_API_KEY` nell'unit.
