# VideoRecap

Convert MOV videos to MP4, extract audio, and generate transcripts and structured meeting reports locally on an Apple Silicon Mac. VideoRecap also accepts M4A recordings, including iPhone voice recordings.

Transcription uses Qwen3-ASR through MLX, with automatic language detection. Reports are written in Italian by default, following the editable instructions in `prompt_sintesi.txt`. Models run directly in Python processes using Metal; no model server is required.

## Requirements

- macOS on Apple Silicon.
- Python 3.10 or later; Python 3.12 is recommended.
- FFmpeg and ffprobe, available through Homebrew.
- An Internet connection to install dependencies and download model weights.
- Enough disk space and unified memory for the selected models. The default 27B summary model requires substantial memory, including room for context, caches, and macOS.

## Quick start

From the project directory:

```sh
brew install ffmpeg python@3.12
./setup_sintesi.sh
```

The setup script creates or reuses `.venv`, installs both transcription and summary dependencies, and downloads the models. For transcription only, use `./setup_asr.sh` instead.

Place `.mov` or `.m4a` files in `input/`, then preview and run:

```sh
./go.sh --anteprima
./go.sh
```

**Dropbox import:** a normal run also moves MOV and M4A files from your Dropbox `Screenshot` folder into the input directory. It checks `~/Library/CloudStorage/Dropbox/Screenshot` first, then `~/Dropbox/Screenshot`. Source files are removed only after a complete transfer. Files whose names already exist in the input directory, including completed files with an `_` prefix, stay in Dropbox. If the Dropbox folder is unavailable, processing continues with the files already in the input directory.

Preview mode does not move or process files. It lists planned imports and processing commands for files already in the input directory. Model downloads are also skipped in preview mode.

## Outputs and reruns

Results are saved in `output/` by default:

| Input | Outputs |
| --- | --- |
| `input/meeting.mov` | `meeting.mp4`, `meeting.m4a`, `meeting.txt`, `meeting.sintesi.md` |
| `input/recording.m4a` | `recording.m4a`, `recording.txt`, `recording.sintesi.md` |

- MOV files are converted to H.264 MP4 on a 1920 × 1080 canvas, preserving aspect ratio with padding, at up to 30 fps. MP4 audio is mono AAC at 160 kbit/s, with faststart enabled for web playback.
- The separate M4A preserves the original first audio track when it is AAC; other audio codecs are converted to AAC at 192 kbit/s. M4A inputs are copied without re-encoding.
- Transcripts are UTF-8 text. Audio is read from the original recording and transcribed in segments of up to 30 seconds.
- Markdown reports include an executive summary, key points, decisions, actions with owners and deadlines, open questions, and optional notes. Long transcripts are summarized in sections and combined into a final report.
- MOV files without audio produce only an MP4.

After all requested steps succeed, the original input is renamed with an `_` prefix, for example `input/meeting.mov` becomes `input/_meeting.mov`. File contents are preserved, and subsequent runs ignore prefixed inputs.

Existing outputs are skipped without being overwritten. Failed steps leave the input name unchanged so you can rerun the command and reuse completed outputs. To regenerate an output, move the existing result out of `output/` and remove the input's `_` prefix if necessary. To regenerate only a report, move its `.sintesi.md` file and use `--solo-sintesi`.

Only files directly inside the input directory are processed; subdirectories are not scanned. Use distinct base names for different recordings: `meeting.mov` and `meeting.m4a` would share output names, so the script rejects this conflict. M4A input and output directories must be different.

## Usage

Command-line options retain their Italian names:

```sh
./go.sh --senza-sintesi           # Transcribe without generating reports
./go.sh --senza-testo             # Convert video and copy/extract audio only
./go.sh --solo-sintesi            # Summarize existing TXT files in output/
./go.sh --lingua English          # Set the transcription language explicitly
./go.sh --anteprima              # Preview without changing files
./go.sh --help
```

`--lingua` controls transcription; edit `prompt_sintesi.txt` to change the report language or structure. `--solo-sintesi` skips media import and conversion and cannot be combined with `--senza-testo` or `--senza-sintesi`.

Use custom input and output directories:

```sh
./go.sh "/path/to/recordings" --output "/path/to/results"
./go.sh --solo-sintesi --output "/path/to/transcripts"
```

Default directories are resolved relative to the script, even when it is launched from another directory. Dropbox import also applies when a custom input directory is provided.

Summarize a single transcript, optionally choosing a destination and prompt:

```sh
.venv/bin/python sintetizza_testo.py "/path/to/meeting.txt"
.venv/bin/python sintetizza_testo.py meeting.txt report.md --prompt prompt_sintesi.txt
```

The default destination for a single transcript is `meeting.sintesi.md` beside the source file. Direct Python commands use models already available locally; `go.sh` automatically downloads missing or incomplete models required for the selected mode. Missing dependencies still require the setup scripts.

## Configuration

| Environment variable | Default / purpose |
| --- | --- |
| `MODELLO_ASR` | `Qwen/Qwen3-ASR-1.7B` |
| `MODELLO_SINTESI` | `mlx-community/Qwen3.5-27B-6bit` |
| `HF_HOME` | `.cache/huggingface` inside the project |
| `PYTHON_SETUP` | Python interpreter used to create `.venv`; automatically selected if unset |
| `NTFY_URL` | Optional ntfy topic URL for completion notifications |

Model variables accept Hugging Face repository IDs or complete local directories containing configuration, tokenizer files, and compatible safetensors weights. GGUF weights are not supported. Use the same model and cache settings during setup and execution, for example:

```sh
MODELLO_ASR=/path/to/asr MODELLO_SINTESI=/path/to/summary ./go.sh
```

The summary model uses a 32,768-token context, an input budget of up to 24,000 tokens including instructions and template, and up to 4,096 output tokens. Empty, truncated, or thinking-tag-containing summary responses are rejected. Section-based summarization may omit secondary details; use the transcript to check precise statements.

For ntfy notifications, set `NTFY_URL` or save your topic URL as a single line in the local `.ntfy-url` file. The environment variable takes precedence. Without either setting, notifications are disabled. Notifications send only a completion message, without audio, transcripts, or reports. Notification failures do not change the processing result.

## Local data and cleanup

Audio and transcripts are processed on your Mac. Once dependencies and complete model weights are available, local processing does not require a network connection; model downloads and optional ntfy notifications do.

The `input/` and `output/` contents, virtual environment, caches, model weights, and personal configuration are excluded from Git. Keep personal recordings, transcripts, and reports in these directories.

```sh
./clean.sh
```

This deletes the project's `.cache` directory, including model weights stored there. `go.sh` downloads required missing weights again on the next run. A custom `HF_HOME` outside the project cache is unaffected.

## Verification

Offline tests do not require models, a GPU, or MLX dependencies:

```sh
python3 -m unittest discover -s tests -v
```

GitHub Actions runs these tests and checks shell script syntax on pushes and pull requests.

For more detailed behavior and model notes in Italian, see [LEGGIMI.txt](LEGGIMI.txt).
