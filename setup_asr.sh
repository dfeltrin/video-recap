#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/setup_ambiente.sh"
"$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements-asr.txt"
"$PYTHON" "$SCRIPT_DIR/modelli_locali.py" --scarica asr
echo 'ASR locale pronto. È necessario FFmpeg: brew install ffmpeg'
