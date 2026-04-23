#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# install_cajero_kiosk.sh
# Configura un usuario cajero con auto-login y kiosk mode.
#
# Uso:
#   sudo bash configSO/install_cajero_kiosk.sh
#   sudo bash configSO/install_cajero_kiosk.sh --user cajero --password 'Clave123!'
###############################################################################

KIOSK_USER="cajero"
KIOSK_PASSWORD="cajero123"
ADMIN_USER="admin"
APP_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      KIOSK_USER="$2"
      shift 2
      ;;
    --password)
      KIOSK_PASSWORD="$2"
      shift 2
      ;;
    --admin-user)
      ADMIN_USER="$2"
      shift 2
      ;;
    --app-path)
      APP_PATH="$2"
      shift 2
      ;;
    -h|--help)
      echo "Uso: sudo bash configSO/install_cajero_kiosk.sh [--user U] [--password P] [--admin-user A] [--app-path RUTA]"
      exit 0
      ;;
    *)
      echo "Parametro desconocido: $1"
      exit 1
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: ejecutar como root (sudo)."
  exit 1
fi

if [[ -z "$APP_PATH" ]]; then
  APP_PATH="/home/${ADMIN_USER}/expendedoraExperimental"
fi

echo "=============================================="
echo "Configuracion Kiosk Expendedora"
echo "=============================================="
echo "Usuario kiosk : ${KIOSK_USER}"
echo "Admin user    : ${ADMIN_USER}"
echo "App path      : ${APP_PATH}"
echo ""

echo "[1/8] Instalando paquetes requeridos..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  lightdm \
  lxsession \
  wmctrl \
  unclutter \
  xdotool \
  python3 \
  python3-tk >/dev/null

echo "[2/8] Creando usuario kiosk..."
if id "${KIOSK_USER}" >/dev/null 2>&1; then
  echo " - Usuario ${KIOSK_USER} ya existe."
else
  useradd -m -s /bin/bash "${KIOSK_USER}"
  echo " - Usuario ${KIOSK_USER} creado."
fi
echo "${KIOSK_USER}:${KIOSK_PASSWORD}" | chpasswd

echo "[3/8] Configurando auto-login en LightDM..."
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-expendedora-kiosk.conf <<EOF
[Seat:*]
autologin-user=${KIOSK_USER}
autologin-user-timeout=0
user-session=LXDE-pi
EOF

echo "[4/8] Preparando launcher kiosk..."
KIOSK_HOME="/home/${KIOSK_USER}"
LAUNCHER="${KIOSK_HOME}/launch_expendedora_kiosk.sh"

cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

APP_PATH="${APP_PATH}"
LOG_FILE="\${HOME}/expendedora-kiosk.log"

sleep 4
export DISPLAY=:0

xset s off || true
xset -dpms || true
xset s noblank || true
unclutter -idle 0.2 -root || true

start_app() {
  cd "\${APP_PATH}"
  if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
  fi
  nohup python3 main.py >> "\${LOG_FILE}" 2>&1 &
  APP_PID=\$!
}

fullscreen_app() {
  local win
  win=\$(wmctrl -lx | awk '/python|tk|expendedora/i {print \$1; exit}')
  if [[ -n "\${win:-}" ]]; then
    wmctrl -i -r "\${win}" -b add,fullscreen,maximized_vert,maximized_horz || true
    wmctrl -i -a "\${win}" || true
  fi
}

start_app
sleep 2
fullscreen_app

while true; do
  if ! ps -p "\${APP_PID}" >/dev/null 2>&1; then
    start_app
    sleep 2
  fi
  fullscreen_app
  sleep 2
done
EOF

chmod 0755 "${LAUNCHER}"
chown "${KIOSK_USER}:${KIOSK_USER}" "${LAUNCHER}"

echo "[5/8] Configurando autostart..."
AUTOSTART_DIR="${KIOSK_HOME}/.config/autostart"
mkdir -p "${AUTOSTART_DIR}"
cat > "${AUTOSTART_DIR}/expendedora-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Expendedora Kiosk
Exec=${LAUNCHER}
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
chown -R "${KIOSK_USER}:${KIOSK_USER}" "${KIOSK_HOME}/.config"

echo "[6/8] Ajustando permisos de app..."
if [[ -d "${APP_PATH}" ]]; then
  chmod -R a+rX "${APP_PATH}" || true
else
  echo "ADVERTENCIA: no existe APP_PATH (${APP_PATH}). Ajustalo con --app-path."
fi

echo "[7/8] Agregando usuario a grupo gpio (si existe)..."
if getent group gpio >/dev/null 2>&1; then
  usermod -aG gpio "${KIOSK_USER}"
fi

echo "[8/8] Configuracion finalizada."
echo ""
echo "Ejecuta para aplicar:"
echo "  sudo reboot"
echo ""
echo "Usuario: ${KIOSK_USER}"
echo "Password: ${KIOSK_PASSWORD}"
echo ""
echo "Recomendado luego de probar:"
echo "  sudo passwd ${KIOSK_USER}"
