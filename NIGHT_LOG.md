# DANTE — registro del turno di notte (sviluppo autonomo)

Antonio ha autorizzato lo sviluppo autonomo notturno su 4 aree. Questo file è la
memoria condivisa tra i risvegli: backlog + cosa è già fatto. Aggiornalo sempre.

## Paletti (NON derogare)
1. Ogni deploy: verifica che il servizio `dante-web` resti `active` + smoke test.
   Se si rompe → **rollback immediato** (git checkout del file + redeploy + restart).
2. Commit a ogni miglioria funzionante (messaggi chiari, co-author trailer).
3. Crediti ElevenLabs col contagocce: NON testare voce/STT in loop. Usa test testuali
   (WebSocket) e, se serve audio, Piper locale. Mai esaurire il piano free.
4. NON toccare: segreti/.env, sicurezza SSH del box, config credenziali, scelta voce.
5. Log qui di ogni intervento (data/ora la mette il sistema nei commit).
6. Fermarsi quando Antonio lo dice.

## Stato attuale (baseline)
- Voce ElevenLabs turbo_v2_5 (George), STT Scribe, snapshot infra live compatta,
  modello Sonnet, UI voice-first con orb 3D. Latenza turno ~5s.

## Backlog (in ordine di priorità)

### Interfaccia (ho gli screenshot: web/../scratchpad/shot/shot.js)
- [x] Icone dock in SVG (mic/tastiera/altoparlante/menu) invece di emoji: nitide, coerenti
      su ogni OS/browser, + aria-label. Verificato via screenshot. FATTO.
- [ ] Rivedere composizione/estetica orb con screenshot iterativi
- [ ] Rendere leggibili/eleganti gli stati (badge connessione, hint)
- [ ] Stati di errore/caricamento chiari (es. "voce non disponibile", quota EL finita)
- [ ] Layout mobile/responsive verificato
- [ ] Micro-animazioni transizioni di fase

### Robustezza & affidabilità
- [x] Circuit breaker ElevenLabs: su 429/errore salta EL per 5 min → Piper/Whisper senza
      chiamate fallite ripetute. /health mostra cloud_voice attiva/cooldown. FATTO, verificato.
- [x] Riconnessione WebSocket robusta: backoff esponenziale (max 15s), niente timer
      doppi, onerror→close, reset stato se cade a metà turno. FATTO, verificato.
- [ ] Resilienza snapshot poller (già try/except; aggiungere timestamp/età snapshot)
- [x] Test automatici (pytest): gate permessi, formattatori Virtualizor, config/persona.
      8 test, tutti verdi. tests/ + requirements-dev.txt. FATTO.
- [x] /health arricchito: stt/tts attivi + snapshot_age_s. FATTO, verificato.

### Osservabilità (snapshot)
- [x] Rilevamento soglie: disco >80%, RAM >85%, VPS non online → riga "DA GUARDARE"/"Nessun
      allarme" in cima alla snapshot + percentuali per VPS. FATTO, verificato.
- [ ] Banda per VPS nella snapshot
- [x] Soglie sul nodo fisico (RAM >85%, disco >80%) → confluiscono nella riga alert.
      Refactor snapshot: helper in cima, dati nodo raw riusati. FATTO, verificato.

### Pulizia + documentazione
- [ ] Rimuovere codice morto (mood off, riferimenti Whisper primario)
- [ ] Aggiornare README/CLAUDE/DEPLOY all'architettura attuale (Scribe, turbo, snapshot)
- [ ] Coerenza commenti/naming

## Fatto (log progressi)
- UI: icone dock da emoji a SVG inline (coerenti/crisp + accessibilità). Verificato con screenshot headless.
- Osservabilità: soglie anche sul nodo fisico (RAM/disco) nella riga alert; refactor snapshot builder. Deploy verificato.
- Robustezza: riconnessione WS con backoff esponenziale + reset stato su caduta a metà turno. Deploy verificato (WS ready ok).
- Robustezza: suite pytest (8 test) su gate/formattatori/config. Tutti verdi. Zero deploy (test locali).
- Robustezza: circuit breaker ElevenLabs (cooldown 5min su fallimento) in /stt e /tts; /health espone cloud_voice. Deploy verificato.
- Robustezza: /health ora riporta motori STT/TTS attivi + età snapshot; timestamp snapshot aggiunto. Deploy verificato.
- (inizio turno) creato NIGHT_LOG.md
- Osservabilità: snapshot con riga alert (soglie disco/RAM/online) + % per VPS. Deploy
  verificato (servizio active, smoke test: DANTE riferisce "nessun allarme"). Commit fatto.
