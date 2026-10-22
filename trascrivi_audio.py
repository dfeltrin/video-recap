#!/usr/bin/env python3
"""Trascrizione locale con Qwen3-ASR 1.7B eseguito direttamente con MLX."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from modelli_locali import MODELLO_ASR, percorso_modello, verifica


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sorgente", type=Path)
    parser.add_argument("destinazione", type=Path)
    parser.add_argument("--lingua", default=None, help="Es. Italian, English; predefinita: automatica.")
    args = parser.parse_args()
    verifica([MODELLO_ASR])
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg non trovato. Installalo con: brew install ffmpeg")
    if not args.sorgente.is_file():
        raise ValueError("Audio sorgente non trovato: {}".format(args.sorgente))
    from mlx_qwen3_asr import Session
    import numpy as np
    print("Caricamento del modello ASR in memoria…", flush=True)
    sessione = Session(model=str(percorso_modello(MODELLO_ASR)))
    testi = []
    inizio = time.monotonic()
    # Segmenti PCM da 30 secondi: memoria limitata anche per registrazioni lunghe.
    with tempfile.TemporaryFile() as errori:
        processo = subprocess.Popen(
            [ffmpeg, "-v", "error", "-nostdin", "-i", str(args.sorgente),
             "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=errori)
        try:
            numero = 0
            while True:
                pcm = processo.stdout.read(16000 * 2 * 30)
                if not pcm:
                    break
                numero += 1
                audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
                risposta = sessione.transcribe(audio, language=args.lingua, max_new_tokens=4096)
                if risposta.truncated:
                    raise RuntimeError("Trascrizione troncata: risultato non pubblicato.")
                testi.append(risposta.text.strip())
                print("ASR: {} segmenti | {} | {:.0f}s".format(numero, risposta.language, time.monotonic() - inizio), flush=True)
            if processo.wait() != 0:
                errori.seek(0)
                raise RuntimeError("Estrazione audio fallita: " + errori.read().decode(errors="replace"))
        finally:
            processo.stdout.close()
            if processo.poll() is None:
                processo.terminate()
                try:
                    processo.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    processo.kill()
                    processo.wait()
    if not testi or not any(testi):
        raise RuntimeError("Nessun segmento audio da trascrivere.")
    with args.destinazione.open("x", encoding="utf-8") as testo:
        testo.write("\n".join(testi).strip() + "\n")
    print("Trascrizione completata.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print("Errore trascrizione: {}".format(exc), file=sys.stderr)
        sys.exit(1)
