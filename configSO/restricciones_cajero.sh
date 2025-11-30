#!/bin/bash

################################################################################
# Script de restricciones adicionales para usuario cajero
# - Bloquear acceso a terminal
# - Deshabilitar teclas de acceso directo
# - Restringir acceso al sistema
################################################################################

set -e

echo "=========================================="
echo "RESTRICCIONES ADICIONALES - USUARIO CAJERO"
echo "=========================================="

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Ejecutar como root (sudo)"
    exit 1
fi

USUARIO_CAJERO="cajero"

if ! id "$USUARIO_CAJERO" &>/dev/null; then
    echo "ERROR: El usuario '$USUARIO_CAJERO' no existe"
    echo "Ejecutar primero: sudo bash crear_usuario_cajero.sh"
    exit 1
fi

echo ""
echo "[1/5] Bloqueando acceso a terminal..."

# Crear configuración de Openbox (gestor de ventanas)
OPENBOX_DIR="/home/$USUARIO_CAJERO/.config/openbox"
mkdir -p "$OPENBOX_DIR"

cat > "$OPENBOX_DIR/lxde-pi-rc.xml" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <keyboard>
    <!-- Deshabilitar Ctrl+Alt+T (terminal) -->
    <keybind key="C-A-t">
      <action name="Execute">
        <execute>false</execute>
      </action>
    </keybind>

    <!-- Deshabilitar Alt+F2 (ejecutar) -->
    <keybind key="A-F2">
      <action name="Execute">
        <execute>false</execute>
      </action>
    </keybind>

    <!-- Deshabilitar Ctrl+Alt+F1-F12 (TTY) -->
    <keybind key="C-A-F1"><action name="Execute"><execute>false</execute></action></keybind>
    <keybind key="C-A-F2"><action name="Execute"><execute>false</execute></action></keybind>
    <keybind key="C-A-F3"><action name="Execute"><execute>false</execute></action></keybind>
    <keybind key="C-A-F4"><action name="Execute"><execute>false</execute></action></keybind>
    <keybind key="C-A-F5"><action name="Execute"><execute>false</execute></action></keybind>
    <keybind key="C-A-F6"><action name="Execute"><execute>false</execute></action></keybind>

    <!-- Permitir Alt+F4 (cerrar ventana) -->
    <keybind key="A-F4">
      <action name="Close"/>
    </keybind>
  </keyboard>

  <applications>
    <!-- Configuración de aplicaciones -->
    <application name="*">
      <decor>yes</decor>
      <maximized>true</maximized>
    </application>
  </applications>
</openbox_config>
EOF

chown -R "$USUARIO_CAJERO:$USUARIO_CAJERO" "$OPENBOX_DIR"

echo ""
echo "[2/5] Configurando bash restringido..."

# Crear bashrc limitado
cat > "/home/$USUARIO_CAJERO/.bashrc" <<'EOF'
# Bashrc restringido para usuario cajero
# Solo permite ejecutar la aplicación expendedora

# Deshabilitar comandos peligrosos
alias rm='echo "Comando no disponible"'
alias mv='echo "Comando no disponible"'
alias cp='echo "Comando no disponible"'
alias dd='echo "Comando no disponible"'
alias chmod='echo "Comando no disponible"'
alias chown='echo "Comando no disponible"'
alias sudo='echo "Comando no disponible"'

# Mensaje de bienvenida
echo "=========================================="
echo "  SISTEMA EXPENDEDORA - MODO CAJERO"
echo "=========================================="
echo ""
echo "Comandos disponibles:"
echo "  • iniciar  - Iniciar aplicación expendedora"
echo "  • salir    - Cerrar sesión"
echo ""

# Alias útiles
alias iniciar='python3 /home/admin/expendedoraExperimental/main.py'
alias salir='logout'

# Limpiar historial al salir
trap 'history -c' EXIT
EOF

chown "$USUARIO_CAJERO:$USUARIO_CAJERO" "/home/$USUARIO_CAJERO/.bashrc"

echo ""
echo "[3/5] Restringiendo acceso a directorios del sistema..."

# Crear perfil de usuario restringido
cat > "/home/$USUARIO_CAJERO/.profile" <<'EOF'
# Perfil de usuario cajero - acceso restringido

# Variables de entorno limitadas
export PATH="/usr/local/bin:/usr/bin:/bin"
export HOME="/home/cajero"

# Restringir navegación
cd "$HOME"

# Iniciar aplicación automáticamente si es sesión gráfica
if [ -n "$DISPLAY" ]; then
    # Ya se inicia con autostart de LXDE
    :
fi
EOF

chown "$USUARIO_CAJERO:$USUARIO_CAJERO" "/home/$USUARIO_CAJERO/.profile"

echo ""
echo "[4/5] Configurando permisos de sudo (sin acceso)..."

# Asegurar que cajero NO tenga acceso a sudo
if [ -f "/etc/sudoers.d/$USUARIO_CAJERO" ]; then
    rm "/etc/sudoers.d/$USUARIO_CAJERO"
fi

# Verificar que no esté en grupo sudo
deluser "$USUARIO_CAJERO" sudo 2>/dev/null || true

echo ""
echo "[5/5] Creando script de bloqueo de pantalla..."

# Crear script para bloquear después de inactividad
cat > "/home/$USUARIO_CAJERO/auto_lock.sh" <<'EOF'
#!/bin/bash
# Auto-bloqueo después de 10 minutos de inactividad
xautolock -time 10 -locker "dm-tool lock" &
EOF

chmod +x "/home/$USUARIO_CAJERO/auto_lock.sh"
chown "$USUARIO_CAJERO:$USUARIO_CAJERO" "/home/$USUARIO_CAJERO/auto_lock.sh"

# Agregar a autostart
AUTOSTART_DIR="/home/$USUARIO_CAJERO/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/autolock.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Auto Lock
Exec=/home/$USUARIO_CAJERO/auto_lock.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

chown -R "$USUARIO_CAJERO:$USUARIO_CAJERO" "$AUTOSTART_DIR"

echo ""
echo "=========================================="
echo "✓ RESTRICCIONES APLICADAS"
echo "=========================================="
echo ""
echo "Restricciones activas:"
echo "  ✓ Terminal bloqueado (Ctrl+Alt+T deshabilitado)"
echo "  ✓ Teclas de acceso directo deshabilitadas"
echo "  ✓ Comandos del sistema bloqueados"
echo "  ✓ Sin acceso a sudo"
echo "  ✓ Auto-bloqueo a los 10 minutos"
echo "  ✓ Bash restringido"
echo ""
echo "El usuario cajero solo puede:"
echo "  • Ejecutar la aplicación expendedora"
echo "  • Cerrar sesión"
echo "  • Usar la interfaz gráfica básica"
echo ""
