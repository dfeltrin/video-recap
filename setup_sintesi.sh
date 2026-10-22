#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sh "$SCRIPT_DIR/setup_asr.sh"
. "$SCRIPT_DIR/setup_ambiente.sh"
"$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements-sintesi.txt"
"$PYTHON" "$SCRIPT_DIR/modelli_locali.py" --scarica sintesi
echo 'Modelli locali MLX pronti. Avvia ./go.sh.'
