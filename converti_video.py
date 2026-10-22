#!/usr/bin/env python3
"""Elabora MOV e M4A: video MP4, audio, trascrizioni TXT e sintesi Markdown."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

FORMATI_INPUT = {".mov", ".m4a"}


def durata_video(sorgente):
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        risultato = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(sorgente)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        durata = float(risultato.stdout.strip())
        return durata if durata > 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def orario(secondi):
    secondi = max(0, int(secondi))
    ore, resto = divmod(secondi, 3600)
    minuti, secondi = divmod(resto, 60)
    return "{:02d}:{:02d}:{:02d}".format(ore, minuti, secondi)


def converti_con_avanzamento(cmd, durata):
    cmd = list(cmd)
    cmd[1:1] = ["-loglevel", "error", "-nostats", "-stats_period", "1",
                "-progress", "pipe:1"]
    inizio = time.monotonic()
    dati = {}
    ultimo = None
    interattivo = sys.stdout.isatty()

    def mostra(finito=False):
        nonlocal ultimo
        trascorso = time.monotonic() - inizio
        try:
            posizione = max(0, int(dati.get("out_time_us", "0")) / 1_000_000)
        except ValueError:
            posizione = 0
        velocita = posizione / trascorso if trascorso > 0 else 0
        stato = "Trascorso {}".format(orario(trascorso))
        if durata:
            percentuale = 100 if finito else min(99.9, posizione / durata * 100)
            residuo = orario(max(0, durata - posizione) / velocita) if velocita > 0 else "in stima"
            stato = "{:5.1f}% | {} | Residuo {}".format(percentuale, stato, "00:00:00" if finito else residuo)
        else:
            stato += " | Video elaborato {}".format(orario(posizione))
        if velocita > 0:
            stato += " | Velocità {:.2f}x".format(velocita)
        # Nei log senza terminale limita gli aggiornamenti a uno ogni 10 secondi.
        if finito or interattivo or ultimo is None or trascorso - ultimo >= 10:
            print(("\r" if interattivo else "") + stato.ljust(100),
                  end="" if interattivo else "\n", flush=True)
            ultimo = trascorso

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1) as processo:
        try:
            mostra()
            for riga in processo.stdout:
                chiave, separatore, valore = riga.strip().partition("=")
                if separatore:
                    dati[chiave] = valore
                if chiave == "progress":
                    mostra()
            codice = processo.wait()
            if codice:
                raise subprocess.CalledProcessError(codice, cmd)
            mostra(finito=True)
        except BaseException:
            if processo.poll() is None:
                processo.terminate()
                try:
                    processo.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    processo.kill()
                    processo.wait()
            raise
        finally:
            if interattivo:
                print(flush=True)


def comando(ffmpeg, sorgente, destinazione):
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-n", "-i", str(sorgente),
        "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "0",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-profile:v", "main", "-level:v", "4.0", "-pix_fmt", "yuv420p",
        "-fpsmax", "30", "-fps_mode", "cfr", "-g", "300",
        "-maxrate", "20M", "-bufsize", "25M",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "1",
        "-movflags", "+faststart", str(destinazione),
    ]


def codec_audio(sorgente):
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise OSError("Per rilevare la traccia audio serve ffprobe: brew install ffmpeg")
    risultato = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of",
         "default=noprint_wrappers=1:nokey=1", str(sorgente)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return risultato.stdout.strip()


def comando_audio(ffmpeg, sorgente, destinazione, codec):
    codifica = ["-c:a", "copy"] if codec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
    return [ffmpeg, "-hide_banner", "-nostdin", "-n", "-i", str(sorgente),
            "-map", "0:a:0", "-vn", "-map_metadata", "0"] + codifica + [
                "-movflags", "+faststart", str(destinazione)]


def comando_testo(sorgente, destinazione, lingua):
    base = Path(__file__).resolve().parent
    python_asr = base / ".venv" / "bin" / "python"
    cmd = [str(python_asr) if python_asr.is_file() else sys.executable,
           str(base / "trascrivi_audio.py"), str(sorgente), str(destinazione)]
    if lingua:
        cmd += ["--lingua", lingua]
    return cmd


def comando_sintesi(sorgente, destinazione):
    base = Path(__file__).resolve().parent
    python = base / ".venv" / "bin" / "python"
    return [str(python) if python.is_file() else sys.executable,
            str(base / "sintetizza_testo.py"), str(sorgente), str(destinazione)]


def file_esistente(destinazione):
    if destinazione.parent.is_dir():
        return next((p for p in destinazione.parent.iterdir()
                     if p.name.casefold() == destinazione.name.casefold()), None)
    return None


def solo_sintesi(uscita, anteprima):
    if not uscita.is_dir():
        raise OSError("La cartella delle trascrizioni non esiste: {}".format(uscita))
    testi = sorted((p for p in uscita.iterdir() if p.is_file()
                    and p.suffix.lower() == ".txt" and not p.name.lower().endswith(".sintesi.txt")),
                   key=lambda p: p.name.lower())
    errori = completati = 0
    for testo in testi:
        destinazione = testo.with_suffix(".sintesi.md")
        if file_esistente(destinazione):
            print("SALTO: {} esiste già.".format(destinazione.name), flush=True)
            continue
        cmd = comando_sintesi(testo, destinazione)
        if anteprima:
            print(shlex.join(cmd))
            continue
        try:
            esegui_trascrizione(cmd)
            completati += 1
        except (subprocess.SubprocessError, OSError) as exc:
            errori += 1
            print("ERRORE per {}: {}".format(destinazione.name, exc), file=sys.stderr)
    print("Completato: {} sintesi, {} errori, {} trascrizioni trovate.".format(
        completati, errori, len(testi)), flush=True)
    return 1 if errori else 0


def esegui_trascrizione(cmd):
    # Attende la chiusura del worker anche dopo Ctrl+C prima di pulire il temporaneo.
    with subprocess.Popen(cmd) as processo:
        try:
            codice = processo.wait()
            if codice:
                raise subprocess.CalledProcessError(codice, cmd)
        except BaseException:
            if processo.poll() is None:
                processo.terminate()
                try:
                    processo.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    processo.kill()
                    processo.wait()
            raise


def segna_completato(sorgente):
    destinazione = sorgente.with_name("_" + sorgente.name)
    if any(p.name.casefold() == destinazione.name.casefold() for p in sorgente.parent.iterdir()):
        raise FileExistsError("Il nome {} è già occupato".format(destinazione.name))
    # Stesso filesystem: nessuna copia dell’originale e nessuna sovrascrittura,
    # anche se un altro processo crea la destinazione nel frattempo.
    os.link(str(sorgente), str(destinazione), follow_symlinks=False)
    try:
        sorgente.unlink()
    except OSError:
        destinazione.unlink()
        raise
    return destinazione


def tempo_impiegato(secondi):
    millisecondi = max(0, round(secondi * 1000))
    ore, resto = divmod(millisecondi, 3_600_000)
    minuti, resto = divmod(resto, 60_000)
    secondi, millisecondi = divmod(resto, 1000)
    return "{:02d}:{:02d}:{:02d}.{:03d}".format(ore, minuti, secondi, millisecondi)


def importa_media_dropbox(cartella, anteprima=False):
    home = Path.home()
    sorgenti = [home / "Library" / "CloudStorage" / "Dropbox" / "Screenshot",
                home / "Dropbox" / "Screenshot"]
    screenshot = next((p for p in sorgenti if p.is_dir()), None)
    if screenshot is None:
        print("IMPORTAZIONE: cartella Screenshot di Dropbox non trovata.", flush=True)
        return
    presenti = {p.name.casefold() for p in cartella.iterdir()} if cartella.exists() else set()
    for sorgente in sorted(screenshot.iterdir(), key=lambda p: p.name.lower()):
        if not sorgente.is_file() or sorgente.suffix.lower() not in FORMATI_INPUT:
            continue
        if sorgente.name.casefold() in presenti or ("_" + sorgente.name).casefold() in presenti:
            continue
        destinazione = cartella / sorgente.name
        if anteprima:
            print("DA SPOSTARE: {} → {}".format(sorgente, destinazione), flush=True)
            continue
        cartella.mkdir(parents=True, exist_ok=True)
        # Completa il trasferimento senza sovrascrivere prima di rimuovere la sorgente.
        with tempfile.TemporaryDirectory(prefix=".importazione-", dir=str(cartella)) as tmp:
            parziale = Path(tmp) / sorgente.name
            shutil.copy2(sorgente, parziale)
            os.link(str(parziale), str(destinazione))
        sorgente.unlink()
        presenti.add(sorgente.name.casefold())
        print("SPOSTATO: {} → {}".format(sorgente, destinazione), flush=True)


def esegui():
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path(__file__).resolve().parent
    parser.add_argument("cartella", nargs="?", type=Path,
                        default=base / "input",
                        help="Cartella di MOV e M4A (predefinita: input accanto allo script).")
    parser.add_argument("--output", type=Path, default=base / "output",
                        help="Cartella di MP4, M4A, TXT e sintesi Markdown (predefinita: output accanto allo script).")
    parser.add_argument("--senza-testo", action="store_true", help="Converte video e audio senza trascrivere.")
    parser.add_argument("--senza-sintesi", action="store_true", help="Trascrive senza generare la sintesi Markdown.")
    parser.add_argument("--solo-sintesi", action="store_true",
                        help="Sintetizza i TXT già in output, senza importare o elaborare MOV/M4A.")
    parser.add_argument("--lingua", default=None, help="Lingua ASR, es. Italian; predefinita: automatica.")
    parser.add_argument("--scarica-modelli", action="store_true",
                        help="Scarica i modelli necessari se mancanti o incompleti (attivo in go.sh).")
    parser.add_argument("--anteprima", action="store_true",
                        help="Mostra i comandi senza convertire; funziona anche senza FFmpeg.")
    args = parser.parse_args()
    if args.solo_sintesi and (args.senza_testo or args.senza_sintesi):
        parser.error("--solo-sintesi non è compatibile con --senza-testo o --senza-sintesi")
    if not args.anteprima and not args.senza_testo:
        from modelli_locali import MODELLO_ASR, MODELLO_SINTESI, verifica
        modelli = [] if args.solo_sintesi else [MODELLO_ASR]
        if not args.senza_sintesi:
            modelli.append(MODELLO_SINTESI)
        try:
            verifica(modelli, scarica=args.scarica_modelli)
        except RuntimeError as exc:
            parser.error(str(exc))
    cartella = args.cartella.expanduser().resolve()
    uscita = args.output.expanduser().resolve()
    if args.solo_sintesi:
        try:
            return solo_sintesi(uscita, args.anteprima)
        except OSError as exc:
            parser.error(str(exc))
    try:
        importa_media_dropbox(cartella, anteprima=args.anteprima)
    except OSError as exc:
        parser.error("Importazione MOV/M4A da Dropbox non riuscita: {}".format(exc))
    if not cartella.is_dir():
        parser.error("La cartella non esiste: {}".format(cartella))
    sorgenti = sorted((p for p in cartella.iterdir()
                       if p.is_file() and p.suffix.lower() in FORMATI_INPUT and not p.name.startswith("_")),
                      key=lambda p: p.name.lower())
    if not sorgenti:
        print("Nessun file MOV o M4A da elaborare in {} (i nomi con prefisso _ vengono ignorati).".format(cartella))
        return 0
    if cartella == uscita and any(p.suffix.lower() == ".m4a" for p in sorgenti):
        parser.error("Per gli input M4A scegli una cartella --output diversa dalla cartella input.")
    # MOV e M4A condividono i nomi degli output: non riutilizzare per errore
    # la trascrizione di un altro input, inclusi quelli già completati.
    for sorgente in sorgenti:
        omonimi = [p for p in cartella.iterdir() if p.is_file() and p != sorgente
                   and p.suffix.lower() in FORMATI_INPUT
                   and p.stem.removeprefix("_").casefold() == sorgente.stem.casefold()]
        if omonimi:
            parser.error("Input con lo stesso nome base: {} e {}. Rinomina uno dei file per distinguere gli output.".format(
                sorgente.name, omonimi[0].name))
    if uscita.exists() and not uscita.is_dir():
        parser.error("La destinazione non è una cartella: {}".format(uscita))
    if not args.anteprima:
        try:
            uscita.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            parser.error("Impossibile creare la cartella di output: {}".format(exc))
    ffmpeg = shutil.which("ffmpeg")
    convertiti = estratti = copiati = trascritti = sintetizzati = saltati = errori = 0
    completati = []
    for numero, sorgente in enumerate(sorgenti, start=1):
        solo_audio = sorgente.suffix.lower() == ".m4a"
        estensioni = [".m4a"] if solo_audio else [".mp4", ".m4a"]
        if not args.senza_testo:
            estensioni.append(".txt")
            if not args.senza_sintesi:
                estensioni.append(".sintesi.md")
        errori_prima = errori
        durata = None
        for estensione in estensioni:
            inizio_step = time.monotonic()
            destinazione = uscita / sorgente.with_suffix(estensione).name
            # Ogni risultato viene controllato separatamente, anche dopo un'interruzione.
            if file_esistente(destinazione):
                print("SALTO: {} esiste già. Tempo controllo: {}".format(
                    destinazione.name, tempo_impiegato(time.monotonic() - inizio_step)), flush=True)
                saltati += 1
                continue
            try:
                codec = codec_audio(sorgente) if estensione in (".m4a", ".txt", ".sintesi.md") else None
                if codec == "" and solo_audio:
                    raise OSError("Il file M4A non contiene una traccia audio leggibile.")
                if codec == "":
                    print("NESSUN AUDIO: {} — {} saltato.".format(sorgente.name, estensione), flush=True)
                    continue
                if estensione == ".sintesi.md":
                    trascrizione = uscita / sorgente.with_suffix(".txt").name
                    trascrizione = file_esistente(trascrizione) or trascrizione
                    if not args.anteprima and not trascrizione.is_file():
                        raise OSError("Trascrizione mancante: {}".format(trascrizione.name))
                    crea_comando = lambda target: comando_sintesi(trascrizione, target)
                elif estensione == ".txt":
                    crea_comando = lambda target: comando_testo(sorgente, target, args.lingua)
                elif estensione == ".m4a" and solo_audio:
                    crea_comando = lambda target: ["cp", "-p", str(sorgente), str(target)]
                elif estensione == ".m4a":
                    crea_comando = lambda target: comando_audio(ffmpeg or "ffmpeg", sorgente, target, codec)
                else:
                    crea_comando = lambda target: comando(ffmpeg or "ffmpeg", sorgente, target)
                if args.anteprima:
                    print(shlex.join(crea_comando(destinazione)))
                    continue
                if not ffmpeg:
                    print("FFmpeg non trovato. Installalo con: brew install ffmpeg", file=sys.stderr)
                    return 2
                azione = {".mp4": "CONVERTO", ".m4a": "ESTRAGGO AUDIO", ".txt": "TRASCRIVO",
                          ".sintesi.md": "SINTETIZZO"}[estensione]
                if solo_audio and estensione == ".m4a":
                    azione = "COPIO AUDIO"
                print("{} [{}/{}]: {} → {}".format(azione, numero, len(sorgenti), sorgente.name, destinazione.name), flush=True)
                if durata is None:
                    durata = durata_video(sorgente)
                # Pubblica solo risultati completi, senza sovrascrivere file esistenti.
                with tempfile.TemporaryDirectory(prefix=".conversione-", dir=str(uscita)) as tmp:
                    parziale = Path(tmp) / ("risultato" + estensione)
                    if solo_audio and estensione == ".m4a":
                        shutil.copy2(sorgente, parziale)
                    elif estensione in (".txt", ".sintesi.md"):
                        esegui_trascrizione(crea_comando(parziale))
                    else:
                        converti_con_avanzamento(crea_comando(parziale), durata)
                    if not parziale.is_file() or parziale.stat().st_size == 0:
                        raise OSError("L'elaborazione non ha prodotto un file valido")
                    os.link(str(parziale), str(destinazione))
                if estensione == ".sintesi.md":
                    sintetizzati += 1
                elif estensione == ".txt":
                    trascritti += 1
                elif estensione == ".m4a":
                    if solo_audio:
                        copiati += 1
                    else:
                        estratti += 1
                else:
                    convertiti += 1
            except (subprocess.SubprocessError, OSError) as exc:
                errori += 1
                print("ERRORE per {}: {}".format(destinazione.name, exc), file=sys.stderr)
            finally:
                print("TEMPO STEP {}: {}".format(
                    destinazione.name, tempo_impiegato(time.monotonic() - inizio_step)), flush=True)
        if errori == errori_prima:
            completati.append(sorgente)
        else:
            print("INPUT CONSERVATO: {} — alcuni passaggi non sono riusciti.".format(sorgente.name), flush=True)
    rinominati = 0
    for sorgente in completati:
        if args.anteprima:
            print("AL TERMINE: {} → _{} (solo se tutti i passaggi riescono).".format(sorgente.name, sorgente.name))
            continue
        inizio_rinomina = time.monotonic()
        try:
            nuovo_nome = segna_completato(sorgente)
            rinominati += 1
            print("RINOMINATO: {} → {}".format(sorgente.name, nuovo_nome.name), flush=True)
        except OSError as exc:
            errori += 1
            print("ERRORE rinomina {}: {}".format(sorgente.name, exc), file=sys.stderr)
        finally:
            print("TEMPO RINOMINA {}: {}".format(
                sorgente.name, tempo_impiegato(time.monotonic() - inizio_rinomina)), flush=True)
    print("Completato: {} video convertiti, {} audio estratti, {} audio copiati, {} testi trascritti, {} sintesi, {} file già presenti, {} input rinominati, {} errori.".format(convertiti, estratti, copiati, trascritti, sintetizzati, saltati, rinominati, errori))
    return 1 if errori else 0


def main():
    inizio = time.monotonic()
    try:
        return esegui()
    finally:
        print("TEMPO TOTALE: {}".format(tempo_impiegato(time.monotonic() - inizio)), flush=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nConversione interrotta. Gli originali sono conservati.", file=sys.stderr)
        sys.exit(130)
