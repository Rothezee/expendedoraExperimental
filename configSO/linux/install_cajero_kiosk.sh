#!/usr/bin/env bash
#
# Configura Linux en modo kiosk para la expendedora (usuario cajero).
# - Usuario local limitado
# - Auto-login en el gestor de display (lightdm / gdm3 / sddm)
# - Sesión gráfica que mantiene main.py en ejecución
# - Sin contraseña (opcional, por defecto activado)
#
# Uso (como root):
#   sudo ./configSO/linux/install_cajero_kiosk.sh
#   sudo ./configSO/linux/install_cajero_kiosk.sh --user cajero --app-path /opt/expendedora
#   sudo ./configSO/linux/install_cajero_kiosk.sh --with-password --password 'secreta'
#
set -euo pipefail

KIOSK_USER="cajero"
APP_PATH=""
NO_PASSWORD=1
PASSWORD="cajero123"
WHAT_IF=0
SKIP_AUTOLOGIN=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/templates"
KIOSK_FOLDER="ExpendedoraKiosk"
SERVICE_NAME="expendedora-kiosk.service"

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \?//'
    echo ""
    echo "Opciones:"
    echo "  --user NAME           Usuario kiosk (default: cajero)"
    echo "  --app-path PATH       Ruta del repo (default: raíz del proyecto)"
    echo "  --no-password         Cuenta sin contraseña (default)"
    echo "  --with-password       Crea/actualiza con contraseña"
    echo "  --password PASS       Contraseña si --with-password"
    echo "  --skip-autologin      No tocar autologin del display manager"
    echo "  --what-if             Solo mostrar acciones"
    echo "  -h, --help            Esta ayuda"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) KIOSK_USER="$2"; shift 2 ;;
        --app-path) APP_PATH="$2"; shift 2 ;;
        --no-password) NO_PASSWORD=1; shift ;;
        --with-password) NO_PASSWORD=0; shift ;;
        --password) PASSWORD="$2"; shift 2 ;;
        --skip-autologin) SKIP_AUTOLOGIN=1; shift ;;
        --what-if) WHAT_IF=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; usage; exit 1 ;;
    esac
done

[[ -z "$APP_PATH" ]] && APP_PATH="$REPO_ROOT"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Ejecutá como root: sudo $0" >&2
    exit 1
fi

if [[ ! -f "$APP_PATH/main.py" ]]; then
    echo "No se encontró main.py en: $APP_PATH" >&2
    exit 1
fi

run() {
    if [[ "$WHAT_IF" -eq 1 ]]; then
        echo "  (what-if) $*"
    else
        "$@"
    fi
}

log_step() {
    echo ""
    echo "$1"
}

detect_display_manager() {
    if [[ -f /etc/lightdm/lightdm.conf ]]; then
        echo "lightdm"
    elif [[ -d /etc/gdm3 ]]; then
        echo "gdm3"
    elif [[ -d /etc/sddm.conf.d ]] || [[ -f /etc/sddm.conf ]]; then
        echo "sddm"
    else
        echo ""
    fi
}

configure_lightdm_autologin() {
    local conf="/etc/lightdm/lightdm.conf"
    local dropin_dir="/etc/lightdm/lightdm.conf.d"
    local dropin="$dropin_dir/99-expendedora-kiosk.conf"

    run mkdir -p "$dropin_dir"
    run tee "$dropin" >/dev/null <<EOF
[Seat:*]
autologin-user=$KIOSK_USER
autologin-user-timeout=0
autologin-session=expendedora-kiosk
EOF

    if [[ -f "$conf" ]] && grep -q '^\[Seat:' "$conf" 2>/dev/null; then
        echo "  lightdm: drop-in en $dropin"
    else
        echo "  lightdm: drop-in en $dropin (revisá que lightdm esté instalado)"
    fi
}

configure_gdm_autologin() {
    local custom="/etc/gdm3/custom.conf"
    if [[ ! -f "$custom" ]]; then
        echo "  Aviso: no existe $custom; instalá gdm3 o usá lightdm." >&2
        return 1
    fi
    if [[ "$WHAT_IF" -eq 1 ]]; then
        echo "  (what-if) Habilitar AutomaticLogin=$KIOSK_USER en $custom"
        return 0
    fi
    if grep -q '^AutomaticLogin=' "$custom" 2>/dev/null; then
        sed -i "s/^AutomaticLogin=.*/AutomaticLogin=$KIOSK_USER/" "$custom"
    elif grep -q '^\[daemon\]' "$custom"; then
        sed -i "/^\[daemon\]/a AutomaticLogin=$KIOSK_USER\nAutomaticLoginEnable=true" "$custom"
    else
        printf '\n[daemon]\nAutomaticLogin=%s\nAutomaticLoginEnable=true\n' "$KIOSK_USER" >>"$custom"
    fi
    echo "  gdm3: AutomaticLogin=$KIOSK_USER"
}

configure_sddm_autologin() {
    local conf="/etc/sddm.conf"
    run mkdir -p /etc/sddm.conf.d
    run tee /etc/sddm.conf.d/expendedora-kiosk.conf >/dev/null <<EOF
[Autologin]
User=$KIOSK_USER
Session=expendedora-kiosk
EOF
    echo "  sddm: autologin en /etc/sddm.conf.d/expendedora-kiosk.conf"
}

install_xsession() {
    local xs="/usr/share/xsessions/expendedora-kiosk.desktop"
    local launcher_cmd
    launcher_cmd="/home/$KIOSK_USER/$KIOSK_FOLDER/launch_expendedora_kiosk.sh"

    run tee "$xs" >/dev/null <<EOF
[Desktop Entry]
Name=Expendedora Kiosk
Comment=Kiosk expendedora (solo main.py)
Exec=$launcher_cmd
Type=Application
DesktopNames=expendedora-kiosk
EOF
    echo "  Sesión X: $xs"
}

install_systemd_user_service() {
    local unit_dir="/home/$KIOSK_USER/.config/systemd/user"
    local launcher="/home/$KIOSK_USER/$KIOSK_FOLDER/launch_expendedora_kiosk.sh"
    local unit="$unit_dir/$SERVICE_NAME"

    run mkdir -p "$unit_dir"
    run tee "$unit" >/dev/null <<EOF
[Unit]
Description=Expendedora kiosk launcher
After=graphical-session.target

[Service]
Type=simple
Environment=DISPLAY=:0
ExecStart=$launcher
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

    if [[ "$WHAT_IF" -eq 0 ]]; then
        chown -R "$KIOSK_USER:$KIOSK_USER" "/home/$KIOSK_USER/.config"
        # Habilitar linger para que el servicio de usuario arranque sin login interactivo extra
        loginctl enable-linger "$KIOSK_USER" 2>/dev/null || true
    fi
    echo "  systemd user: $unit"
}

allow_blank_password_pam() {
    # Permite login local con contraseña vacía (necesario para autologin sin clave)
    local pam_files=(/etc/pam.d/common-auth /etc/pam.d/login /etc/pam.d/lightdm /etc/pam.d/gdm-password)
    for f in "${pam_files[@]}"; do
        [[ -f "$f" ]] || continue
        if grep -q 'pam_unix.so' "$f" && ! grep -q 'nullok' "$f"; then
            if [[ "$WHAT_IF" -eq 1 ]]; then
                echo "  (what-if) Añadir nullok en $f (revisar manualmente)"
            else
                sed -i 's/pam_unix\.so\(.*\) obscure/pam_unix.so\1 nullok obscure/' "$f" 2>/dev/null || \
                    sed -i 's/pam_unix\.so/pam_unix.so nullok/' "$f"
                echo "  PAM nullok en $f"
            fi
        fi
    done
}

echo "=============================================="
echo " Configuración Kiosk Expendedora (Linux)"
echo "=============================================="
echo "Usuario kiosk : $KIOSK_USER"
echo "App path      : $APP_PATH"
echo "Sin contraseña: $((NO_PASSWORD))"
echo ""

log_step "[1/7] Creando usuario kiosk..."
if id "$KIOSK_USER" &>/dev/null; then
    echo "  Usuario $KIOSK_USER ya existe."
else
  if [[ "$NO_PASSWORD" -eq 1 ]]; then
    run useradd -m -s /bin/bash -c "Cajero Expendedora" "$KIOSK_USER"
    echo "  Usuario $KIOSK_USER creado."
  else
    run useradd -m -s /bin/bash -c "Cajero Expendedora" "$KIOSK_USER"
    echo "$KIOSK_USER:$PASSWORD" | run chpasswd
    echo "  Usuario $KIOSK_USER creado con contraseña."
  fi
fi

if [[ "$NO_PASSWORD" -eq 1 ]]; then
    log_step "[2/7] Sin contraseña y PAM..."
    run passwd -d "$KIOSK_USER" 2>/dev/null || true
    allow_blank_password_pam
else
    log_step "[2/7] Modo con contraseña..."
    echo "$KIOSK_USER:$PASSWORD" | run chpasswd
fi

log_step "[3/7] Launcher y permisos..."
KIOSK_DIR="/home/$KIOSK_USER/$KIOSK_FOLDER"
if [[ "$WHAT_IF" -eq 0 ]]; then
    mkdir -p "$KIOSK_DIR"
    escaped_app="${APP_PATH//\//\\/}"
    sed "s|__APP_PATH__|$APP_PATH|g" "$TEMPLATE_DIR/launch_expendedora_kiosk.sh" >"$KIOSK_DIR/launch_expendedora_kiosk.sh"
    chmod +x "$KIOSK_DIR/launch_expendedora_kiosk.sh"
    chown -R "$KIOSK_USER:$KIOSK_USER" "$KIOSK_DIR"
    chown -R "$KIOSK_USER:$KIOSK_USER" "/home/$KIOSK_USER"
    chmod -R o+rX "$APP_PATH" 2>/dev/null || true
    usermod -aG video,input,dialout,plugdev "$KIOSK_USER" 2>/dev/null || true
    echo "  Launcher: $KIOSK_DIR/launch_expendedora_kiosk.sh"
else
    echo "  (what-if) Copiar launcher a $KIOSK_DIR"
fi

log_step "[4/7] Sesión gráfica kiosk..."
install_xsession

# .xsession del usuario como respaldo si el DM no usa la sesión custom
if [[ "$WHAT_IF" -eq 0 ]]; then
    echo "exec $KIOSK_DIR/launch_expendedora_kiosk.sh" >"/home/$KIOSK_USER/.xsession"
    chmod +x "/home/$KIOSK_USER/.xsession"
    chown "$KIOSK_USER:$KIOSK_USER" "/home/$KIOSK_USER/.xsession"
fi

log_step "[5/7] Auto-login..."
if [[ "$SKIP_AUTOLOGIN" -eq 1 ]]; then
    echo "  Omitido (--skip-autologin)."
else
    dm="$(detect_display_manager)"
    case "$dm" in
        lightdm) configure_lightdm_autologin ;;
        gdm3) configure_gdm_autologin ;;
        sddm) configure_sddm_autologin ;;
        *)
            echo "  No se detectó lightdm/gdm3/sddm."
            echo "  Configurá autologin manualmente para el usuario $KIOSK_USER"
            echo "  y sesión 'expendedora-kiosk'."
            ;;
    esac
fi

log_step "[6/7] Servicio systemd (respaldo)..."
install_systemd_user_service

log_step "[7/7] Energía (no suspender)..."
if command -v systemctl >/dev/null 2>&1; then
    run systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true
fi
if [[ -f /etc/systemd/logind.conf ]]; then
    if ! grep -q '^HandleLidSwitch=ignore' /etc/systemd/logind.conf 2>/dev/null; then
        run mkdir -p /etc/systemd/logind.conf.d
        run tee /etc/systemd/logind.conf.d/expendedora-kiosk.conf >/dev/null <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
IdleAction=ignore
EOF
    fi
fi

echo ""
echo "Listo."
echo ""
echo "Próximos pasos:"
echo "  1. Reiniciá: sudo reboot"
echo "  2. Debería entrar al usuario $KIOSK_USER y abrir la expendedora."
echo ""
if [[ "$NO_PASSWORD" -eq 1 ]]; then
    echo "Contraseña Linux: (sin contraseña)"
    echo "Aviso: cualquiera con acceso físico puede entrar a la sesión."
else
    echo "Contraseña: $PASSWORD"
fi
echo ""
echo "Desinstalar: sudo $SCRIPT_DIR/uninstall_cajero_kiosk.sh --user $KIOSK_USER"
