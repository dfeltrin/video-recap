#!/usr/bin/env python3
"""Sintetizza una trascrizione in Markdown con Qwen3.5 27B locale via MLX."""

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parent
LIMITE_INPUT = 24000
MAX_OUTPUT = 4096


def dividi_testo(testo, tokenizer, limite):
    """Divide senza perdere caratteri o spezzare parole, rispettando i token."""
    if len(tokenizer.encode(testo, add_special_tokens=False)) <= limite:
        return [testo]
    parole = re.findall(r"\s*\S+|\s+$", testo)
    parti = []
    inizio = 0
    while inizio < len(parole):
        basso, alto = inizio + 1, len(parole)
        fine = inizio
        while basso <= alto:
            medio = (basso + alto) // 2
            candidato = "".join(parole[inizio:medio])
            if len(tokenizer.encode(candidato, add_special_tokens=False)) <= limite:
                fine, basso = medio, medio + 1
            else:
                alto = medio - 1
        if fine == inizio:
            raise ValueError("Una parola supera il limite di contesto: impossibile dividerla senza alterarla.")
        parti.append("".join(parole[inizio:fine]))
        inizio = fine
    return parti


def sintetizza(testo, istruzioni):
    from modelli_locali import SintesiLocale
    sessione = SintesiLocale()
    tokenizer = sessione.tokenizer

    def prompt(contenuto, parziale=False, aggregato=False):
        contesto = "Trascrizione da elaborare:"
        if aggregato:
            contesto = ("Produci un unico documento finale dalle sintesi parziali in ordine "
                        "cronologico. Unisci i duplicati e non trasformare ipotesi in decisioni.")
        elif parziale:
            contesto = ("Questa è una porzione di una trascrizione più lunga. Conserva fatti, "
                        "termini tecnici, decisioni, azioni, responsabili, scadenze e dubbi.")
        return [{"role": "system", "content": istruzioni},
                {"role": "user", "content": contesto + "\n\n" + contenuto}]

    def dimensione(messaggi):
        return len(sessione.prepara(messaggi))

    def genera(contenuto, etichetta, parziale=False, aggregato=False):
        messaggi = prompt(contenuto, parziale, aggregato)
        if dimensione(messaggi) > LIMITE_INPUT:
            raise ValueError("Il prompt supera il budget di input in token.")
        risultato = sessione.genera(messaggi, etichetta, MAX_OUTPUT)
        if not risultato:
            raise RuntimeError("Risposta vuota: risultato non pubblicato.")
        return risultato

    # Riserva spazio alle istruzioni e al template; input e output restano sotto 32K.
    budget = LIMITE_INPUT - max(dimensione(prompt("", True)), dimensione(prompt("", aggregato=True)),
                               dimensione(prompt(""))) - 128
    if budget < 1024:
        raise ValueError("Prompt troppo lungo: manca spazio per la trascrizione.")
    contenuto = testo
    aggregato = False
    for livello in range(8):
        parti = dividi_testo(contenuto, tokenizer, budget)
        if len(parti) == 1:
            return genera(contenuto, "Sintesi finale", aggregato=aggregato)
        print("Testo lungo: {} sezioni, livello {}.".format(len(parti), livello + 1), flush=True)
        risultati = [genera(parte, "Sintesi sezione {}/{}".format(i, len(parti)),
                            parziale=True, aggregato=aggregato)
                     for i, parte in enumerate(parti, 1)]
        ridotto = "\n\n".join("SEZIONE {}\n{}".format(i, parte)
                                for i, parte in enumerate(risultati, 1))
        if len(tokenizer.encode(ridotto)) >= len(tokenizer.encode(contenuto)):
            raise RuntimeError("Le sintesi parziali non riducono il testo: risultato non pubblicato.")
        contenuto, aggregato = ridotto, True
    raise RuntimeError("Troppe riduzioni necessarie: risultato non pubblicato.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sorgente", type=Path)
    parser.add_argument("destinazione", type=Path, nargs="?",
                        help="Predefinita: nome.sintesi.md accanto alla trascrizione.")
    parser.add_argument("--prompt", type=Path, default=BASE / "prompt_sintesi.txt")
    args = parser.parse_args()
    destinazione = args.destinazione or args.sorgente.with_suffix(".sintesi.md")
    if destinazione.exists():
        print("SALTO: {} esiste già.".format(destinazione), flush=True)
        return 0
    testo = args.sorgente.read_text(encoding="utf-8").strip()
    istruzioni = args.prompt.read_text(encoding="utf-8").strip()
    if not testo or not istruzioni:
        raise ValueError("Trascrizione e prompt devono contenere testo.")
    risultato = sintetizza(testo, istruzioni)
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sintesi-", dir=str(destinazione.parent)) as tmp:
        parziale = Path(tmp) / "risultato.md"
        parziale.write_text(risultato + "\n", encoding="utf-8")
        os.link(str(parziale), str(destinazione))
    print("SINTESI SALVATA: {}".format(destinazione), flush=True)
    return 0


if __name__ == "__main__":
    inizio = time.monotonic()
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print("Errore sintesi: {}".format(exc), file=sys.stderr)
        sys.exit(1)
    finally:
        print("TEMPO SINTESI: {:.1f}s".format(time.monotonic() - inizio), flush=True)
