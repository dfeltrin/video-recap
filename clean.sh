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

# Cancella tutta la cache locale del progetto, inclusi i pesi dei modelli.
rm -rf -- "$SCRIPT_DIR/.cache"
printf 'Cache del progetto eliminata: %s\n' "$SCRIPT_DIR/.cache"
