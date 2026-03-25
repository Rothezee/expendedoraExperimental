#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Ejecutar como root: sudo bash updater/systemd/install_updater_timer.sh"
  exit 1
fi

SERVICE_SRC="$(pwd)/updater/systemd/expendedora-updater.service"
TIMER_SRC="$(pwd)/updater/systemd/expendedora-updater.timer"

cp "$SERVICE_SRC" /etc/systemd/system/expendedora-updater.service
cp "$TIMER_SRC" /etc/systemd/system/expendedora-updater.timer

systemctl daemon-reload
systemctl enable --now expendedora-updater.timer
systemctl status expendedora-updater.timer --no-pager

echo "Updater timer instalado."

