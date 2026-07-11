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
- [ ] Rivedere composizione/estetica orb con screenshot iterativi
- [ ] Rendere leggibili/eleganti gli stati (badge connessione, hint)
- [ ] Stati di errore/caricamento chiari (es. "voce non disponibile", quota EL finita)
- [ ] Layout mobile/responsive verificato
- [ ] Micro-animazioni transizioni di fase

### Robustezza & affidabilità
- [ ] Gestione quota ElevenLabs (429) con messaggio UI chiaro + fallback trasparente
- [ ] Riconnessione WebSocket robusta (già base; irrobustire)
- [ ] Resilienza snapshot poller (già try/except; aggiungere timestamp/età snapshot)
- [ ] Test automatici (pytest) su: gate permessi, formattatori vz, routing STT/TTS
- [x] /health arricchito: stt/tts attivi + snapshot_age_s. FATTO, verificato.

### Osservabilità (snapshot)
- [x] Rilevamento soglie: disco >80%, RAM >85%, VPS non online → riga "DA GUARDARE"/"Nessun
      allarme" in cima alla snapshot + percentuali per VPS. FATTO, verificato.
- [ ] Banda per VPS nella snapshot
- [ ] Soglie anche sul nodo fisico (RAM/disco del nodo)

### Pulizia + documentazione
- [ ] Rimuovere codice morto (mood off, riferimenti Whisper primario)
- [ ] Aggiornare README/CLAUDE/DEPLOY all'architettura attuale (Scribe, turbo, snapshot)
- [ ] Coerenza commenti/naming

## Fatto (log progressi)
- Robustezza: /health ora riporta motori STT/TTS attivi + età snapshot; timestamp snapshot aggiunto. Deploy verificato.
- (inizio turno) creato NIGHT_LOG.md
- Osservabilità: snapshot con riga alert (soglie disco/RAM/online) + % per VPS. Deploy
  verificato (servizio active, smoke test: DANTE riferisce "nessun allarme"). Commit fatto.
