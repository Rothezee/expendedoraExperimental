#!/usr/bin/env bash
# Launcher kiosk Expendedora (Linux)
set -u

APP_PATH="__APP_PATH__"
RESTART_DELAY_SECONDS="${RESTART_DELAY_SECONDS:-3}"
LOG_FILE="${EXPENDEDORA_KIOSK_LOG:-$HOME/expendedora-kiosk.log}"

log() {
    local line
    line="$(date '+%Y-%m-%d %H:%M:%S') $*"
    echo "$line"
    echo "$line" >>"$LOG_FILE" 2>/dev/null || true
}

resolve_python() {
    if [[ -n "${EXPENDEDORA_PYTHON:-}" && -x "${EXPENDEDORA_PYTHON}" ]]; then
        echo "${EXPENDEDORA_PYTHON}"
        return 0
    fi
    local venv_py="$APP_PATH/.venv/bin/python"
    if [[ -x "$venv_py" ]]; then
        echo "$venv_py"
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi
    if command -v python >/dev/null 2>&1; then
        command -v python
        return 0
    fi
    return 1
}

disable_screen_blank() {
    if command -v xset >/dev/null 2>&1; then
        xset s off 2>/dev/null || true
        xset -dpms 2>/dev/null || true
        xset s noblank 2>/dev/null || true
    fi
}

hide_cursor() {
    if command -v unclutter >/dev/null 2>&1; then
        unclutter -idle 0.1 -root >/dev/null 2>&1 &
    fi
}

log "=== Inicio launcher kiosk ==="
log "AppPath=$APP_PATH Usuario=${USER:-?} DISPLAY=${DISPLAY:-}"

if [[ ! -d "$APP_PATH" ]]; then
    log "ERROR: AppPath no existe: $APP_PATH"
    sleep 30
    exit 1
fi

main_py="$APP_PATH/main.py"
if [[ ! -f "$main_py" ]]; then
    log "ERROR: No se encontró main.py en $APP_PATH"
    sleep 30
    exit 1
fi

if ! python_cmd="$(resolve_python)"; then
    log "ERROR: No se encontró Python (python3/python o .venv)."
    sleep 60
    exit 1
fi

disable_screen_blank
hide_cursor

cd "$APP_PATH" || exit 1

while true; do
    log "Iniciando expendedora ($python_cmd)..."
    if "$python_cmd" "$main_py"; then
        code=$?
    else
        code=$?
    fi
    log "Proceso finalizado con código $code"
    log "Reiniciando en ${RESTART_DELAY_SECONDS}s..."
    sleep "$RESTART_DELAY_SECONDS"
done
