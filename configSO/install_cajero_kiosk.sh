#!/usr/bin/env bash
#
# Instalador kiosk multiplataforma.
# - Linux: bash nativo (autologin + usuario sin contraseña por defecto)
# - Windows (Git Bash / MSYS): delega al script PowerShell existente
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NO_PASSWORD=1
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-password) NO_PASSWORD=1; shift ;;
        --with-password) NO_PASSWORD=0; shift ;;
        -h|--help)
            echo "Uso: $0 [--no-password|--with-password] [más opciones del instalador]"
            echo ""
            echo "Linux:"
            echo "  sudo $SCRIPT_DIR/linux/install_cajero_kiosk.sh --no-password"
            echo ""
            echo "Windows (PowerShell como Administrador):"
            echo "  powershell -ExecutionPolicy Bypass -File $SCRIPT_DIR/windows/install_cajero_kiosk.ps1 -NoPassword"
            exit 0
            ;;
        *) EXTRA_ARGS+=("$1"); shift ;;
    esac
done

uname_s="$(uname -s 2>/dev/null || echo unknown)"

case "$uname_s" in
    Linux)
        args=(--no-password)
        [[ "$NO_PASSWORD" -eq 0 ]] && args=(--with-password)
        exec "$SCRIPT_DIR/linux/install_cajero_kiosk.sh" "${args[@]}" "${EXTRA_ARGS[@]}"
        ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT)
        ps1="$SCRIPT_DIR/windows/install_cajero_kiosk.ps1"
        if [[ ! -f "$ps1" ]]; then
            echo "No se encontró: $ps1" >&2
            exit 1
        fi
        pw_args=(-ExecutionPolicy Bypass -File "$ps1")
        if [[ "$NO_PASSWORD" -eq 1 ]]; then
            pw_args+=(-NoPassword)
        fi
        if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
            pw_args+=("${EXTRA_ARGS[@]}")
        fi
        echo "Windows: ejecutando PowerShell (requiere Administrador)..."
        powershell.exe "${pw_args[@]}"
        ;;
    *)
        echo "Sistema no soportado: $uname_s" >&2
        echo "Usá linux/install_cajero_kiosk.sh o windows/install_cajero_kiosk.ps1" >&2
        exit 1
        ;;
esac
