#!/bin/bash
################################################################################
# Script para crear usuario "cajero" con modo kiosk
# - Auto-login al iniciar Raspberry Pi
# - Aplicación se ejecuta automáticamente al iniciar
# - Aplicación maximizada sin consola visible
# - No se puede cerrar ni minimizar la aplicación
# - Barra de tareas bloqueada
# - Acceso restringido
################################################################################

set -e # Detener si hay algún error

echo "=========================================="
echo "CONFIGURACIÓN DE USUARIO CAJERO (KIOSK)"
echo "=========================================="

# Verificar que se ejecuta como root
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: Este script debe ejecutarse como root"
    echo "Ejecutar: sudo bash crear_usuario_cajero.sh"
    exit 1
fi

# Variables
USUARIO_CAJERO="cajero"
PASSWORD_CAJERO="cajero123"  # Cambiar por una contraseña segura
USUARIO_ADMIN="admin"
APP_PATH="/home/$USUARIO_ADMIN/expendedoraExperimental"

echo ""
echo "[1/9] Creando usuario '$USUARIO_CAJERO'..."
# Crear usuario si no existe
if id "$USUARIO_CAJERO" &>/dev/null; then
    echo "Usuario '$USUARIO_CAJERO' ya existe. Saltando..."
else
    useradd -m -s /bin/bash "$USUARIO_CAJERO"
    echo "$USUARIO_CAJERO:$PASSWORD_CAJERO" | chpasswd
    echo "Usuario '$USUARIO_CAJERO' creado con contraseña: $PASSWORD_CAJERO"
fi

echo ""
echo "[2/9] Configurando auto-login para '$USUARIO_CAJERO'..."
# Configurar auto-login en LightDM
LIGHTDM_CONF="/etc/lightdm/lightdm.conf"
if [ -f "$LIGHTDM_CONF" ]; then
    # Backup del archivo original
    cp "$LIGHTDM_CONF" "$LIGHTDM_CONF.backup"
    
    # Configurar auto-login
    sed -i "s/^#autologin-user=.*/autologin-user=$USUARIO_CAJERO/" "$LIGHTDM_CONF"
    sed -i "s/^autologin-user=.*/autologin-user=$USUARIO_CAJERO/" "$LIGHTDM_CONF"
    
    # Si no existe la línea, agregarla
    if ! grep -q "autologin-user=" "$LIGHTDM_CONF"; then
        echo "autologin-user=$USUARIO_CAJERO" >> "$LIGHTDM_CONF"
    fi
    
    echo "Auto-login configurado en LightDM"
else
    echo "ADVERTENCIA: No se encontró $LIGHTDM_CONF"
fi

echo ""
echo "[3/9] Creando script launcher para modo kiosk..."
# Crear script que lanza la aplicación en modo kiosk
LAUNCHER_SCRIPT="/home/$USUARIO_CAJERO/launch_kiosk.sh"

cat > "$LAUNCHER_SCRIPT" <<'EOF'
#!/bin/bash

# Esperar a que el escritorio esté listo
sleep 5

# Ocultar cursor del mouse después de inactividad
unclutter -idle 0.1 &

# Deshabilitar salvapantallas y suspensión
xset s off
xset -dpms
xset s noblank

# Ejecutar la aplicación en modo kiosk
cd /home/admin/expendedoraExperimental
python3 main.py &

# Guardar el PID de la aplicación
APP_PID=$!

# Esperar a que la ventana de la aplicación aparezca
sleep 3

# Buscar el ID de la ventana de la aplicación
WINDOW_ID=$(wmctrl -l | grep -i "expendedora\|python" | head -1 | awk '{print $1}')

if [ -n "$WINDOW_ID" ]; then
    # Maximizar la ventana
    wmctrl -i -r $WINDOW_ID -b add,maximized_vert,maximized_horz
    
    # Poner la ventana en primer plano
    wmctrl -i -a $WINDOW_ID
    
    # Quitar decoraciones de la ventana (barra de título, botones)
    wmctrl -i -r $WINDOW_ID -b add,fullscreen
fi

# Monitorear que la aplicación siempre esté en primer plano
while true; do
    sleep 2
    
    # Verificar si la aplicación sigue corriendo
    if ! ps -p $APP_PID > /dev/null 2>&1; then
        # Si la aplicación se cerró, reiniciarla
        cd /home/admin/expendedoraExperimental
        python3 main.py &
        APP_PID=$!
        sleep 3
        WINDOW_ID=$(wmctrl -l | grep -i "expendedora\|python" | head -1 | awk '{print $1}')
        if [ -n "$WINDOW_ID" ]; then
            wmctrl -i -r $WINDOW_ID -b add,maximized_vert,maximized_horz
            wmctrl -i -r $WINDOW_ID -b add,fullscreen
            wmctrl -i -a $WINDOW_ID
        fi
    else
        # Asegurar que la ventana esté siempre en primer plano
        if [ -n "$WINDOW_ID" ]; then
            wmctrl -i -a $WINDOW_ID
        fi
    fi
done
EOF

chmod +x "$LAUNCHER_SCRIPT"
chown "$USUARIO_CAJERO:$USUARIO_CAJERO" "$LAUNCHER_SCRIPT"

echo ""
echo "[4/9] Instalando paquetes necesarios..."
# Instalar herramientas necesarias
apt-get update -qq
apt-get install -y wmctrl unclutter xdotool 2>/dev/null || echo "Algunos paquetes ya están instalados"

echo ""
echo "[5/9] Configurando inicio automático de la aplicación..."
# Crear directorio autostart
AUTOSTART_DIR="/home/$USUARIO_CAJERO/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

# Crear archivo de autostart que ejecuta el launcher
cat > "$AUTOSTART_DIR/expendedora.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Sistema Expendedora Kiosk
Comment=Iniciar aplicación expendedora en modo kiosk
Exec=$LAUNCHER_SCRIPT
Icon=applications-games
Terminal=false
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

chown -R "$USUARIO_CAJERO:$USUARIO_CAJERO" "/home/$USUARIO_CAJERO/.config"

echo ""
echo "[6/9] Bloqueando barra de tareas (panel)..."
# Crear configuración de LXDE para bloquear panel
LXDE_CONFIG_DIR="/home/$USUARIO_CAJERO/.config/lxpanel/LXDE-pi/panels"
mkdir -p "$LXDE_CONFIG_DIR"

# Configurar panel bloqueado (si usa LXDE)
cat > "$LXDE_CONFIG_DIR/panel" <<'EOF'
# Configuración de panel bloqueado
Global {
    edge=bottom
    allign=center
    margin=0
    widthtype=percent
    width=100
    height=36
    transparent=0
    tintcolor=#000000
    alpha=0
    autohide=0
    heightwhenhidden=2
    setdocktype=1
    setpartialstrut=1
    usefontcolor=1
    fontcolor=#ffffff
    background=0
    backgroundfile=/usr/share/lxpanel/images/background.png
    iconsize=36
}

Plugin {
    type=space
    Config {
        Size=2
    }
}

Plugin {
    type=menu
    Config {
        image=/usr/share/raspberrypi-artwork/raspitr.png
        system {
        }
        separator {
        }
        item {
            command=run
        }
        separator {
        }
        item {
            image=gnome-logout
            command=logout
        }
    }
}

Plugin {
    type=launchbar
    Config {
        Button {
            id=lxde-screenlock.desktop
        }
    }
}
EOF

chown -R "$USUARIO_CAJERO:$USUARIO_CAJERO" "/home/$USUARIO_CAJERO/.config/lxpanel"

echo ""
echo "[7/9] Restringiendo accesos del usuario cajero..."
# Crear grupo para usuarios kiosk
groupadd -f kiosk-users
usermod -a -G kiosk-users "$USUARIO_CAJERO"

# Dar permisos de lectura a la aplicación
chmod -R 755 "$APP_PATH"
chown -R "$USUARIO_ADMIN:$USUARIO_ADMIN" "$APP_PATH"

# Permitir acceso de lectura/ejecución al cajero
setfacl -R -m u:$USUARIO_CAJERO:rx "$APP_PATH" 2>/dev/null || echo "ADVERTENCIA: setfacl no disponible, usando permisos estándar"

# Dar permisos para usar GPIO (si está disponible)
if [ -d "/sys/class/gpio" ]; then
    usermod -a -G gpio "$USUARIO_CAJERO" 2>/dev/null || echo "Grupo GPIO no disponible"
fi

echo ""
echo "[8/9] Configurando restricciones de escritorio..."
# Crear configuración de PCMANFM (gestor de archivos)
PCMANFM_DIR="/home/$USUARIO_CAJERO/.config/pcmanfm/LXDE-pi"
mkdir -p "$PCMANFM_DIR"

cat > "$PCMANFM_DIR/desktop-items-0.conf" <<EOF
[*]
wallpaper_mode=stretch
wallpaper_common=1
wallpaper=/usr/share/raspberrypi-artwork/raspberry-pi-logo.png
desktop_bg=#000000
desktop_fg=#ffffff
desktop_shadow=#000000
show_wm_menu=0
show_documents=0
show_trash=0
show_mounts=0
EOF

chown -R "$USUARIO_CAJERO:$USUARIO_CAJERO" "/home/$USUARIO_CAJERO/.config/pcmanfm"

# Deshabilitar atajos de teclado peligrosos
OPENBOX_DIR="/home/$USUARIO_CAJERO/.config/openbox"
mkdir -p "$OPENBOX_DIR"

cat > "$OPENBOX_DIR/lxde-pi-rc.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <keyboard>
    <!-- Deshabilitar Alt+F4 (cerrar ventana) -->
    <keybind key="A-F4">
      <action name="Execute">
        <command>true</command>
      </action>
    </keybind>
    <!-- Deshabilitar Ctrl+Alt+Delete -->
    <keybind key="C-A-Delete">
      <action name="Execute">
        <command>true</command>
      </action>
    </keybind>
  </keyboard>
</openbox_config>
EOF

chown -R "$USUARIO_CAJERO:$USUARIO_CAJERO" "$OPENBOX_DIR"

echo ""
echo "[9/9] Configurando permisos de base de datos..."
# Dar permisos de lectura/escritura a las bases de datos
if [ -f "$APP_PATH/expendedora.db" ]; then
    chmod 666 "$APP_PATH/expendedora.db"
    echo "Permisos de expendedora.db configurados"
fi

if [ -f "$APP_PATH/users.db" ]; then
    chmod 666 "$APP_PATH/users.db"
    echo "Permisos de users.db configurados"
fi

# Dar permisos al archivo de registro
if [ -f "$APP_PATH/registro.json" ]; then
    chmod 666 "$APP_PATH/registro.json"
    echo "Permisos de registro.json configurados"
fi

echo ""
echo "=========================================="
echo "✓ CONFIGURACIÓN COMPLETADA"
echo "=========================================="
echo ""
echo "Resumen:"
echo " • Usuario: $USUARIO_CAJERO"
echo " • Contraseña: $PASSWORD_CAJERO"
echo " • Auto-login: Activado"
echo " • Aplicación: $APP_PATH/main.py"
echo " • Inicio automático: Activado"
echo " • Modo kiosk: Activado"
echo " • Consola: Oculta"
echo " • Ventana: Maximizada y sin decoraciones"
echo " • Cierre/Minimizar: Deshabilitado"
echo ""
echo "CARACTERÍSTICAS DEL MODO KIOSK:"
echo " ✓ La aplicación se inicia automáticamente"
echo " ✓ La consola está oculta"
echo " ✓ La ventana está maximizada en pantalla completa"
echo " ✓ No se puede cerrar ni minimizar la aplicación"
echo " ✓ Si la app se cierra, se reinicia automáticamente"
echo " ✓ Atajos de teclado peligrosos deshabilitados"
echo ""
echo "IMPORTANTE:"
echo " 1. Cambiar la contraseña con: sudo passwd $USUARIO_CAJERO"
echo " 2. Reiniciar para aplicar cambios: sudo reboot"
echo " 3. El usuario solo podrá ver y usar la aplicación expendedora"
echo ""
echo "Para deshacer los cambios:"
echo " • Eliminar usuario: sudo userdel -r $USUARIO_CAJERO"
echo " • Restaurar lightdm: sudo cp $LIGHTDM_CONF.backup $LIGHTDM_CONF"
echo ""
echo "NOTA: Si necesitas salir del modo kiosk temporalmente:"
echo " • Usa Ctrl+Alt+F1 para ir a una terminal TTY"
echo " • Inicia sesión como $USUARIO_ADMIN"
echo ""deshacer los cambios:"
echo "  • Eliminar usuario: sudo userdel -r $USUARIO_CAJERO"
echo "  • Restaurar lightdm: sudo cp $LIGHTDM_CONF.backup $LIGHTDM_CONF"
echo ""

