#!/bin/sh
set -eu

SCRIPT_PATH=$0
while :; do
    SCRIPT_DIR=$(CDPATH= cd -P -- "$(dirname -- "$SCRIPT_PATH")" && pwd)
    SCRIPT_PATH="$SCRIPT_DIR/$(basename -- "$SCRIPT_PATH")"
    [ -L "$SCRIPT_PATH" ] || break
    LINK_TARGET=$(readlink "$SCRIPT_PATH")
    case $LINK_TARGET in
        /*) SCRIPT_PATH=$LINK_TARGET ;;
        *) SCRIPT_PATH="$SCRIPT_DIR/$LINK_TARGET" ;;
    esac
done

PYTHON="$SCRIPT_DIR/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3
"$PYTHON" "$SCRIPT_DIR/converti_video.py" --scarica-modelli "$@"

# Configurazione personale esclusa da Git; la variabile ha precedenza.
NTFY_URL=${NTFY_URL:-}
if [ -z "$NTFY_URL" ] && [ -f "$SCRIPT_DIR/.ntfy-url" ]; then
    IFS= read -r NTFY_URL < "$SCRIPT_DIR/.ntfy-url" || :
fi
if [ -n "$NTFY_URL" ]; then
    curl -sS -o /dev/null -H "Title: VideoRecap" -d "Elaborazione completata" "$NTFY_URL" ||
        printf 'Notifica ntfy non inviata.\n' >&2
fi
