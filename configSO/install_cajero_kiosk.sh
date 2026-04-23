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
user-session=rpd-labwc
autologin-session=rpd-labwc
EOF

# Algunas imágenes de Raspberry priorizan /etc/lightdm/lightdm.conf por encima
# de snippets; forzamos también allí para evitar que siga autologueando "clue".
if [[ -f /etc/lightdm/lightdm.conf ]]; then
  sed -i "s/^autologin-user=.*/autologin-user=${KIOSK_USER}/" /etc/lightdm/lightdm.conf || true
  sed -i "s/^#autologin-user=.*/autologin-user=${KIOSK_USER}/" /etc/lightdm/lightdm.conf || true
  sed -i "s/^#autologin-user-timeout=.*/autologin-user-timeout=0/" /etc/lightdm/lightdm.conf || true
  sed -i "s/^autologin-session=.*/autologin-session=rpd-labwc/" /etc/lightdm/lightdm.conf || true
  sed -i "s/^#autologin-session=.*/autologin-session=rpd-labwc/" /etc/lightdm/lightdm.conf || true
fi

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
# Ocultar panel/barra si existe en la sesión.
pkill -f "wf-panel-pi|lxpanel|tint2|waybar" || true

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
  pkill -f "wf-panel-pi|lxpanel|tint2|waybar" || true
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

# Autostart específico para labwc (Raspberry OS nuevo).
mkdir -p "${KIOSK_HOME}/.config/labwc"
cat > "${KIOSK_HOME}/.config/labwc/autostart" <<EOF
#!/bin/sh
${LAUNCHER} &
EOF
chmod +x "${KIOSK_HOME}/.config/labwc/autostart"
chown -R "${KIOSK_USER}:${KIOSK_USER}" "${KIOSK_HOME}/.config/labwc"

# Fallback: ejecutar launcher también desde .xprofile.
cat > "${KIOSK_HOME}/.xprofile" <<EOF
#!/bin/sh
${LAUNCHER} &
EOF
chmod +x "${KIOSK_HOME}/.xprofile"
chown "${KIOSK_USER}:${KIOSK_USER}" "${KIOSK_HOME}/.xprofile"

echo "[6/8] Ajustando permisos de app..."
if [[ -d "${APP_PATH}" ]]; then
  chmod -R a+rX "${APP_PATH}" || true
  # Permite al cajero atravesar directorios del admin (home/Documents).
  chmod o+x "/home/${ADMIN_USER}" || true
  chmod o+x "/home/${ADMIN_USER}/Documents" || true
  apt-get install -y --no-install-recommends acl >/dev/null || true
  setfacl -R -m u:${KIOSK_USER}:rx "${APP_PATH}" || true
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
