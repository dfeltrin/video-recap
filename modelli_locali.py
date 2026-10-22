"""Modelli MLX nel processo Python; download durante il setup o tramite go.sh."""
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time

BASE = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(BASE / ".cache" / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
MODELLO_ASR = os.environ.get("MODELLO_ASR", "Qwen/Qwen3-ASR-1.7B")
MODELLO_SINTESI = os.environ.get("MODELLO_SINTESI", "mlx-community/Qwen3.5-27B-6bit")


def percorso_modello(modello, scarica=False):
    percorso = Path(modello).expanduser()
    if not percorso.is_dir():
        from huggingface_hub import snapshot_download
        try:
            percorso = Path(snapshot_download(
                repo_id=modello, local_files_only=not scarica,
                allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja"]))
        except Exception as exc:
            raise RuntimeError("Modello non disponibile: {}. Esegui ./setup_sintesi.sh "
                               "oppure imposta MODELLO_ASR/MODELLO_SINTESI su una cartella locale. ({})".format(modello, exc)) from exc
    try:
        json.loads((percorso / "config.json").read_text())
        pesi = list(percorso.glob("*.safetensors"))
        if not pesi:
            raise ValueError("pesi safetensors mancanti")
        for indice in percorso.glob("*.safetensors.index.json"):
            nomi = set(json.loads(indice.read_text())["weight_map"].values())
            if any(not (percorso / nome).is_file() for nome in nomi):
                raise ValueError("download dei pesi incompleto")
        if any(p.stat().st_size == 0 for p in pesi):
            raise ValueError("file dei pesi vuoto")
        # Qwen3-ASR usa il tokenizer BPE in due file; i modelli di
        # sintesi possono invece includere il tokenizer unificato.
        tokenizer_unificato = (percorso / "tokenizer.json").is_file()
        tokenizer_bpe = all((percorso / nome).is_file()
                            for nome in ("vocab.json", "merges.txt"))
        if not (tokenizer_unificato or tokenizer_bpe):
            raise ValueError("tokenizer mancante: serve tokenizer.json oppure vocab.json e merges.txt")
    except (OSError, ValueError, KeyError) as exc:
        raise RuntimeError("Modello locale incompleto in {}: {}. Ripeti ./setup_sintesi.sh.".format(percorso, exc)) from exc
    return percorso.resolve()


def verifica(modelli=(), scarica=False):
    if not modelli:
        return
    if sys.version_info < (3, 10) or platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("MLX richiede un Mac Apple Silicon e Python 3.10+. Usa .venv/bin/python o ./go.sh.")
    pacchetti = ["huggingface_hub"]
    if MODELLO_ASR in modelli:
        pacchetti.append("mlx_qwen3_asr")
    if MODELLO_SINTESI in modelli:
        pacchetti.append("mlx_lm")
    if any(importlib.util.find_spec(p) is None for p in pacchetti):
        raise RuntimeError("Dipendenze MLX mancanti. Esegui ./setup_sintesi.sh e avvia ./go.sh.")
    for modello in dict.fromkeys(modelli):
        try:
            percorso = percorso_modello(modello)
        except RuntimeError:
            # Una cartella esplicita incompleta va corretta dall'utente;
            # solo gli identificativi Hugging Face consentono il download.
            if not scarica or Path(modello).expanduser().is_dir():
                raise
            print("Download modello mancante o incompleto: {}".format(modello), flush=True)
            percorso = percorso_modello(modello, scarica=True)
        print("Modello locale pronto: {}".format(percorso), flush=True)


class SintesiLocale:
    def __init__(self):
        verifica([MODELLO_SINTESI])
        from mlx_lm import load
        print("Caricamento del modello di sintesi in memoria…", flush=True)
        self.model, self.tokenizer = load(str(percorso_modello(MODELLO_SINTESI)))

    def prepara(self, messaggi):
        return self.tokenizer.apply_chat_template(
            messaggi, tokenize=True, add_generation_prompt=True, enable_thinking=False)

    def genera(self, messaggi, etichetta, max_output=4096, contesto=32768):
        import mlx.core as mx
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler
        tokens = self.prepara(messaggi)
        if len(tokens) + max_output > contesto:
            raise ValueError("Il prompt e l'output superano il contesto disponibile.")
        mx.random.seed(42)
        inizio = ultimo = time.monotonic()
        frammenti, finale = [], None
        print(etichetta + ": elaborazione locale MLX…", flush=True)
        for evento in stream_generate(self.model, self.tokenizer, tokens,
                                      max_tokens=max_output,
                                      sampler=make_sampler(temp=0.2, top_p=0.9)):
            frammenti.append(evento.text)
            finale = evento
            adesso = time.monotonic()
            if adesso - ultimo >= 10:
                print("{}: generazione in corso | {:.0f}s".format(etichetta, adesso - inizio), flush=True)
                ultimo = adesso
        if finale is None or finale.finish_reason != "stop":
            raise RuntimeError("Risposta incompleta o troncata: risultato non pubblicato.")
        risultato = "".join(frammenti).strip()
        if not risultato or "<think>" in risultato or "</think>" in risultato:
            raise RuntimeError("Risposta vuota o contenente ragionamento interno: risultato non pubblicato.")
        print("{} completata: {} token, {:.1f}s.".format(
            etichetta, finale.generation_tokens, time.monotonic() - inizio), flush=True)
        return risultato


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scarica", choices=["asr", "sintesi"], required=True)
    args = parser.parse_args()
    modello = MODELLO_ASR if args.scarica == "asr" else MODELLO_SINTESI
    try:
        print("Preparazione modello: {}".format(modello), flush=True)
        print("Modello salvato: {}".format(percorso_modello(modello, scarica=True)), flush=True)
    except Exception as exc:
        sys.exit(str(exc))
