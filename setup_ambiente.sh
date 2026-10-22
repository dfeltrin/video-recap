#!/bin/sh
# Da includere dagli script setup; SCRIPT_DIR punta al progetto.
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo 'MLX richiede un Mac Apple Silicon.' >&2
    exit 1
fi
PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON_SETUP=${PYTHON_SETUP:-}
    if [ -z "$PYTHON_SETUP" ]; then
        for candidato in python3.12 python3.13 python3.11 python3.10 python3; do
            if command -v "$candidato" >/dev/null 2>&1 &&
                "$candidato" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
                PYTHON_SETUP=$candidato
                break
            fi
        done
    fi
    if [ -z "$PYTHON_SETUP" ]; then
        echo 'Installa Python 3.12: brew install python@3.12' >&2
        exit 1
    fi
    "$PYTHON_SETUP" -m venv "$SCRIPT_DIR/.venv"
fi
"$PYTHON" -c 'import sys; sys.exit("Serve Python 3.10+ nella .venv") if sys.version_info < (3, 10) else None'
export PIP_CACHE_DIR="$SCRIPT_DIR/.cache/pip"
