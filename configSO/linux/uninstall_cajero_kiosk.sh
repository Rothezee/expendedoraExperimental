#!/usr/bin/env bash
set -euo pipefail

KIOSK_USER="cajero"
REMOVE_USER=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) KIOSK_USER="$2"; shift 2 ;;
        --remove-user) REMOVE_USER=1; shift ;;
        -h|--help)
            echo "Uso: sudo $0 [--user cajero] [--remove-user]"
            exit 0
            ;;
        *) echo "Opción desconocida: $1" >&2; exit 1 ;;
    esac
done

[[ "$(id -u)" -ne 0 ]] && { echo "Ejecutá como root." >&2; exit 1; }

rm -f /etc/lightdm/lightdm.conf.d/99-expendedora-kiosk.conf
rm -f /etc/sddm.conf.d/expendedora-kiosk.conf
rm -f /usr/share/xsessions/expendedora-kiosk.desktop
rm -f /etc/systemd/logind.conf.d/expendedora-kiosk.conf

if id "$KIOSK_USER" &>/dev/null; then
    systemctl --user -M "$KIOSK_USER@" disable expendedora-kiosk.service 2>/dev/null || true
    rm -f "/home/$KIOSK_USER/.config/systemd/user/expendedora-kiosk.service"
    loginctl disable-linger "$KIOSK_USER" 2>/dev/null || true
fi

systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

if [[ "$REMOVE_USER" -eq 1 ]] && id "$KIOSK_USER" &>/dev/null; then
    userdel -r "$KIOSK_USER" 2>/dev/null || userdel "$KIOSK_USER"
    echo "Usuario $KIOSK_USER eliminado."
fi

echo "Kiosk desinstalado. Reiniciá si cambiaste lightdm/gdm."
