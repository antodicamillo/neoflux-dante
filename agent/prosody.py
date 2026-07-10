"""DANTE — lettura leggera dell'"umore" dalla voce (solo prosodia, niente ML pesante).

Idea: NON facciamo speech-emotion-recognition deep learning sulla CPU (troppo lento e
inaffidabile). Estraiamo dal WAV poche feature prosodiche economiche (energia/volume,
ritmo di eloquio, pitch medio e variabilità, pause) e le trasformiamo in una breve
"traccia di umore" testuale da iniettare nel prompt. È Claude, poi, a interpretare
umore + PAROLE della trascrizione e ad adattare il tono.

Dipendenze: solo `numpy` (già presente come dipendenza transitiva di faster-whisper via
ctranslate2) + `wave` della stdlib. Nessun librosa/scipy: import istantaneo, zero peso.

Il WAV atteso è quello che `/stt` produce già con ffmpeg: PCM 16-bit, mono, 16 kHz.
Costo tipico su un clip di 2-5 s: pochi millisecondi. Nessuna latenza percepibile.
"""

from __future__ import annotations

import wave
from typing import Optional

import numpy as np


# ── Lettura WAV (stdlib, nessun decoder esterno) ──────────────────────────────
def _read_wav_mono(path: str) -> tuple[np.ndarray, int]:
    """Ritorna (samples float32 in [-1,1], sample_rate). Gestisce PCM 8/16/32-bit.
    Se stereo, fa il mix mono. Pensato per il WAV mono 16k di ffmpeg, ma tollerante."""
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(n)

    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif width == 1:  # PCM 8-bit è unsigned, centrato su 128
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"sampwidth non supportato: {width}")

    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


# ── Pitch via autocorrelazione (economico, per-frame) ─────────────────────────
def _frame_pitch(frame: np.ndarray, sr: int, fmin: float, fmax: float,
                 voicing_thr: float) -> Optional[float]:
    """F0 di un singolo frame con autocorrelazione normalizzata. None se non "voiced".

    Non è preciso come YIN/pYIN, ma per media/variabilità dell'intonazione basta e
    costa pochissimo. Range plausibile voce umana: ~75-400 Hz."""
    frame = frame - frame.mean()
    energy = float(np.dot(frame, frame))
    if energy < 1e-6:
        return None  # frame di silenzio

    # autocorrelazione via FFT (O(n log n))
    n = len(frame)
    nfft = 1 << (2 * n - 1).bit_length()
    spec = np.fft.rfft(frame, nfft)
    ac = np.fft.irfft(spec * np.conj(spec), nfft)[:n]

    min_lag = max(1, int(sr / fmax))
    max_lag = min(n - 1, int(sr / fmin))
    if max_lag <= min_lag:
        return None

    seg = ac[min_lag:max_lag]
    lag = int(np.argmax(seg)) + min_lag
    peak = ac[lag]
    if ac[0] <= 0 or peak / ac[0] < voicing_thr:
        return None  # non abbastanza periodico → non voiced
    return sr / lag


def extract_prosody(
    wav_path: str,
    transcript: str = "",
    *,
    frame_ms: float = 30.0,
    hop_ms: float = 15.0,
    fmin: float = 75.0,
    fmax: float = 400.0,
    voicing_thr: float = 0.30,
    silence_rel_db: float = 25.0,
) -> dict:
    """Estrae feature prosodiche da un WAV mono e ritorna un dict compatto.

    Ritorna:
        energy       : RMS lineare medio (0..~1)
        loudness_dbfs: volume in dBFS (negativo; 0 = fondo scala)
        loudness_label: 'basso' | 'medio' | 'alto'
        pace_wps     : parole al secondo sul parlato (words / durata voce)
        pitch_hz     : intonazione mediana (Hz) sui frame voiced
        pitch_var    : coefficiente di variazione del pitch (std/mean, adimensionale)
        pause_ratio  : frazione di frame in silenzio (proxy di esitazioni/pause)
        voiced_ratio : frazione di frame con voce periodica
        duration_s   : durata totale del clip
    """
    data, sr = _read_wav_mono(wav_path)
    duration_s = len(data) / sr if sr else 0.0
    out = {
        "energy": 0.0, "loudness_dbfs": -120.0, "loudness_label": "medio",
        "pace_wps": 0.0, "pitch_hz": 0.0, "pitch_var": 0.0,
        "pause_ratio": 0.0, "voiced_ratio": 0.0, "duration_s": round(duration_s, 2),
    }
    if len(data) < sr * 0.2:  # meno di 200 ms: troppo corto per dire qualcosa
        return out

    frame_len = max(1, int(sr * frame_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))
    n_frames = 1 + (len(data) - frame_len) // hop if len(data) >= frame_len else 0
    if n_frames <= 0:
        return out

    # RMS globale e RMS per-frame (per pause/voce)
    rms_global = float(np.sqrt(np.mean(data ** 2)) + 1e-12)
    frame_rms = np.empty(n_frames, dtype=np.float32)
    pitches = []
    for i in range(n_frames):
        seg = data[i * hop: i * hop + frame_len]
        frame_rms[i] = np.sqrt(np.mean(seg ** 2) + 1e-12)
        f0 = _frame_pitch(seg, sr, fmin, fmax, voicing_thr)
        if f0 is not None:
            pitches.append(f0)

    # Soglia di silenzio relativa al frame più forte (robusta al volume del mic)
    peak_rms = float(frame_rms.max())
    sil_thr = peak_rms * (10.0 ** (-silence_rel_db / 20.0))
    speech_mask = frame_rms > sil_thr
    pause_ratio = float(1.0 - speech_mask.mean())

    # Ritmo: parole / "span attivo" = dal primo all'ultimo frame di parlato.
    # Così escludiamo il silenzio iniziale/finale (che falserebbe il conteggio) ma
    # teniamo le pause interne: un eloquio veloce e senza pause → wps alto = concitato.
    idx = np.flatnonzero(speech_mask)
    if idx.size >= 2:
        active_span = (idx[-1] - idx[0] + 1) * hop / sr
    else:
        active_span = duration_s
    active_span = max(active_span, 0.3)

    words = len([t for t in transcript.split() if any(c.isalnum() for c in t)])
    pace_wps = float(words / active_span) if words else 0.0

    # Pitch: mediana robusta + coefficiente di variazione
    if pitches:
        parr = np.array(pitches)
        # scarta outlier grossolani (ottava sbagliata) con clip su percentili
        lo, hi = np.percentile(parr, [10, 90])
        parr = parr[(parr >= lo) & (parr <= hi)] if hi > lo else parr
        pitch_hz = float(np.median(parr))
        pitch_var = float(np.std(parr) / pitch_hz) if pitch_hz > 0 else 0.0
    else:
        pitch_hz = 0.0
        pitch_var = 0.0

    loudness_dbfs = 20.0 * float(np.log10(rms_global))
    if loudness_dbfs < -30.0:
        loud_label = "basso"
    elif loudness_dbfs > -18.0:
        loud_label = "alto"
    else:
        loud_label = "medio"

    out.update({
        "energy": round(rms_global, 4),
        "loudness_dbfs": round(loudness_dbfs, 1),
        "loudness_label": loud_label,
        "pace_wps": round(pace_wps, 2),
        "pitch_hz": round(pitch_hz, 1),
        "pitch_var": round(pitch_var, 3),
        "pause_ratio": round(pause_ratio, 3),
        "voiced_ratio": round(len(pitches) / n_frames, 3),
        "duration_s": round(duration_s, 2),
    })
    return out


# ── Mappatura feature → "traccia di umore" testuale per il prompt ──────────────
# Soglie ROZZE e da tarare sul tuo microfono/utente reale. Vedi note in coda al file.
def mood_phrase(feat: dict) -> str:
    """Descrittore COMPATTO dell'umore (senza cornice), adatto a riempire uno slot
    tipo "[UMORE UTENTE: {...}]" in un system prompt che già spiega come reagire.
    Es.: "parla in modo veloce e concitato, a voce alta — possibile umore: teso/agitato".
    Ritorna '' se il segnale è troppo debole/corto per dire qualcosa di sensato."""
    if feat.get("duration_s", 0) < 0.6 or feat.get("voiced_ratio", 0) < 0.05:
        return ""  # niente di affidabile: meglio tacere che inventare

    pace = feat["pace_wps"]
    pvar = feat["pitch_var"]
    loud = feat["loudness_label"]
    pause = feat["pause_ratio"]

    signals = []

    # Ritmo dell'eloquio (parole/sec sullo span attivo). Conversazione IT tipica
    # ~2.5-3.3 wps. Sotto ~2 = lento/calmo; sopra ~3.6 = veloce/concitato.
    if pace >= 3.6:
        signals.append("parla in modo veloce e concitato")
    elif pace <= 2.0 and pace > 0:
        signals.append("parla lentamente, con calma")

    # Volume
    if loud == "alto":
        signals.append("a voce alta")
    elif loud == "basso":
        signals.append("a voce bassa/sommessa")

    # Variabilità del pitch: molta = enfatico/emotivo, poca = piatto/stanco o freddo.
    if pvar >= 0.28:
        signals.append("con intonazione molto variabile (enfatico o agitato)")
    elif pvar <= 0.08 and pvar > 0:
        signals.append("con tono piatto e monotono (stanco o freddo)")

    # Pause: molte pause = esitazione/incertezza.
    if pause >= 0.45:
        signals.append("con molte pause ed esitazioni")

    # Sintesi qualitativa (etichetta d'insieme, sempre come IPOTESI)
    label = "neutro"
    if pace >= 3.6 and (loud == "alto" or pvar >= 0.28):
        label = "teso/agitato"
    elif pace <= 2.0 and (loud == "basso" or pvar <= 0.08):
        label = "stanco/scoraggiato"
    elif pvar >= 0.28 and loud == "alto":
        label = "energico/coinvolto"
    elif pause >= 0.45:
        label = "incerto/esitante"

    if not signals and label == "neutro":
        return ""

    detail = ", ".join(signals) if signals else "segnali deboli"
    return f"{detail} — possibile umore: {label}"


def mood_hint(feat: dict) -> str:
    """Versione autoconclusiva (con cornice + istruzione) per iniezione stand-alone,
    se NON usi già un sistema-prompt che spiega come reagire. Ritorna '' se debole.
    Se il tuo system prompt gestisce già l'umore, usa `mood_phrase` (più asciutta)."""
    phrase = mood_phrase(feat)
    if not phrase:
        return ""
    return (
        f"[SEGNALE VOCALE — ipotesi, non certezza] L'utente {phrase}. Adatta il tono "
        f"senza commentare esplicitamente il suo stato d'animo se non è opportuno."
    )
