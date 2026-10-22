# VideoRecap

Converte video MOV in MP4, estrae l’audio e produce trascrizioni e sintesi in italiano. Supporta anche registrazioni M4A. Trascrizione e sintesi vengono eseguite localmente con MLX su Mac Apple Silicon.

## Requisiti

- macOS su Apple Silicon e Python 3.10+ (consigliato 3.12).
- FFmpeg e ffprobe.
- Connessione Internet per installare le dipendenze e scaricare i modelli.
- Memoria e spazio disco sufficienti per i modelli: la sintesi usa di default Qwen3.5-27B-6bit e richiede molta memoria unificata.

## Avvio

Dal Terminale, nella cartella del progetto:

```sh
brew install ffmpeg python@3.12
./setup_sintesi.sh
./go.sh --anteprima
./go.sh
```

Inserisci file `.mov` o `.m4a` in `input/`. All’avvio vengono anche importati i MOV e M4A presenti in `Dropbox/Screenshot`: i file vengono spostati, rimuovendo la sorgente dopo il trasferimento completo. L’anteprima mostra le operazioni senza eseguirle.

I risultati vengono salvati in `output/`. Gli originali elaborati con successo vengono rinominati aggiungendo `_`; gli output già esistenti vengono saltati.

```sh
./go.sh --senza-sintesi          # Trascrizione senza report
./go.sh --senza-testo            # Solo conversione e audio
./go.sh --solo-sintesi           # Sintesi dei TXT esistenti in output/
./go.sh --lingua Italian        # Forza la lingua di trascrizione
./go.sh --help
```

Per la sola trascrizione, prepara l’ambiente con `./setup_asr.sh`.

## Configurazione

Variabili opzionali: `MODELLO_ASR`, `MODELLO_SINTESI`, `HF_HOME` e `PYTHON_SETUP`. I modelli predefiniti sono `Qwen/Qwen3-ASR-1.7B` e `mlx-community/Qwen3.5-27B-6bit`. Il prompt del report è in `prompt_sintesi.txt`.

Per ricevere notifiche ntfy, imposta `NTFY_URL` oppure salva l’URL del tuo topic nel file locale `.ntfy-url`. La variabile ha precedenza. Senza configurazione le notifiche sono disattivate; un errore di notifica non fa fallire l’elaborazione.

Video, audio, trascrizioni e report nelle cartelle `input/` e `output/`, ambiente virtuale, cache, pesi e configurazione personale sono esclusi da Git. Mantieni i dati personali in queste cartelle.

`./clean.sh` elimina la cache del progetto, inclusi i pesi dei modelli: al prossimo avvio verranno scaricati nuovamente.

Consulta [LEGGIMI.txt](LEGGIMI.txt) per opzioni, comportamento e dettagli dei modelli.

## Verifica

I test offline non richiedono modelli, GPU o dipendenze MLX:

```sh
python3 -m unittest discover -s tests -v
```

## Push su GitHub

Dopo aver creato una repository vuota su GitHub, configura il suo URL ed esegui il push:

```sh
git remote add origin <URL-DELLA-REPOSITORY>
git push -u origin main
```
