#!/bin/bash

################################################################################
# Script de verificación de configuración del usuario cajero
# Verifica que todas las configuraciones estén correctas
################################################################################

echo "=========================================="
echo "VERIFICACIÓN DE CONFIGURACIÓN - CAJERO"
echo "=========================================="
echo ""

USUARIO_CAJERO="cajero"
APP_PATH="/home/admin/expendedoraExperimental"
ERRORES=0
ADVERTENCIAS=0

# Función para mostrar OK
mostrar_ok() {
    echo "  ✓ $1"
}

# Función para mostrar error
mostrar_error() {
    echo "  ✗ ERROR: $1"
    ((ERRORES++))
}

# Función para mostrar advertencia
mostrar_advertencia() {
    echo "  ⚠ ADVERTENCIA: $1"
    ((ADVERTENCIAS++))
}

echo "[1] Verificando usuario cajero..."
if id "$USUARIO_CAJERO" &>/dev/null; then
    mostrar_ok "Usuario '$USUARIO_CAJERO' existe"

    # Verificar que no está en grupo sudo
    if groups "$USUARIO_CAJERO" | grep -q sudo; then
        mostrar_error "Usuario está en grupo 'sudo' (PELIGRO)"
    else
        mostrar_ok "Usuario NO tiene acceso sudo"
    fi

    # Verificar home directory
    if [ -d "/home/$USUARIO_CAJERO" ]; then
        mostrar_ok "Directorio home existe"
    else
        mostrar_error "Directorio home no existe"
    fi
else
    mostrar_error "Usuario '$USUARIO_CAJERO' no existe"
    echo ""
    echo "Ejecutar: sudo bash crear_usuario_cajero.sh"
    exit 1
fi

echo ""
echo "[2] Verificando auto-login..."
if grep -q "autologin-user=$USUARIO_CAJERO" /etc/lightdm/lightdm.conf 2>/dev/null; then
    mostrar_ok "Auto-login configurado en LightDM"
else
    mostrar_advertencia "Auto-login NO configurado"
fi

echo ""
echo "[3] Verificando aplicación..."
if [ -d "$APP_PATH" ]; then
    mostrar_ok "Directorio de aplicación existe"

    if [ -f "$APP_PATH/main.py" ]; then
        mostrar_ok "Archivo main.py existe"
    else
        mostrar_error "main.py no encontrado"
    fi

    # Verificar permisos de lectura para cajero
    if [ -r "$APP_PATH/main.py" ]; then
        mostrar_ok "Cajero puede leer main.py"
    else
        mostrar_error "Cajero NO puede leer main.py"
    fi
else
    mostrar_error "Directorio de aplicación no existe: $APP_PATH"
fi

echo ""
echo "[4] Verificando bases de datos..."
for db in "expendedora.db" "users.db" "registro.json"; do
    if [ -f "$APP_PATH/$db" ]; then
        if [ -w "$APP_PATH/$db" ] && [ -r "$APP_PATH/$db" ]; then
            mostrar_ok "$db tiene permisos correctos"
        else
            mostrar_error "$db sin permisos de lectura/escritura"
        fi
    else
        mostrar_advertencia "$db no existe (se creará al iniciar)"
    fi
done

echo ""
echo "[5] Verificando acceso directo..."
if [ -f "/home/$USUARIO_CAJERO/Desktop/Expendedora.desktop" ]; then
    mostrar_ok "Acceso directo en escritorio existe"
else
    mostrar_advertencia "Acceso directo no existe"
fi

echo ""
echo "[6] Verificando autostart..."
if [ -f "/home/$USUARIO_CAJERO/.config/autostart/expendedora.desktop" ]; then
    mostrar_ok "Autostart configurado"
else
    mostrar_advertencia "Autostart NO configurado"
fi

echo ""
echo "[7] Verificando restricciones..."
if [ -f "/home/$USUARIO_CAJERO/.config/openbox/lxde-pi-rc.xml" ]; then
    mostrar_ok "Configuración de Openbox existe"
else
    mostrar_advertencia "Restricciones de teclado NO configuradas"
fi

if [ -f "/home/$USUARIO_CAJERO/.bashrc" ]; then
    if grep -q "Comando no disponible" "/home/$USUARIO_CAJERO/.bashrc"; then
        mostrar_ok "Bash restringido configurado"
    else
        mostrar_advertencia "Bash NO está restringido"
    fi
else
    mostrar_advertencia "Archivo .bashrc no existe"
fi

echo ""
echo "[8] Verificando permisos GPIO..."
if groups "$USUARIO_CAJERO" | grep -q gpio; then
    mostrar_ok "Usuario en grupo GPIO"
else
    mostrar_advertencia "Usuario NO en grupo GPIO (puede causar errores)"
fi

echo ""
echo "[9] Verificando contraseña..."
# No podemos verificar si es la predeterminada sin intentar login
echo "  ⓘ  Verificar manualmente que la contraseña fue cambiada"
echo "     Contraseña predeterminada: cajero123"

echo ""
echo "=========================================="
echo "RESUMEN DE VERIFICACIÓN"
echo "=========================================="
echo "  Errores: $ERRORES"
echo "  Advertencias: $ADVERTENCIAS"
echo ""

if [ $ERRORES -eq 0 ]; then
    if [ $ADVERTENCIAS -eq 0 ]; then
        echo "✓ TODO ESTÁ CONFIGURADO CORRECTAMENTE"
        echo ""
        echo "Próximos pasos:"
        echo "  1. Cambiar contraseña: sudo passwd $USUARIO_CAJERO"
        echo "  2. Reiniciar sistema: sudo reboot"
        echo "  3. Verificar que inicia automáticamente"
    else
        echo "⚠ CONFIGURACIÓN FUNCIONAL CON ADVERTENCIAS"
        echo ""
        echo "Revisar las advertencias arriba"
        echo "Para aplicar todas las configuraciones:"
        echo "  1. sudo bash crear_usuario_cajero.sh"
        echo "  2. sudo bash restricciones_cajero.sh"
    fi
else
    echo "✗ HAY ERRORES QUE DEBEN CORREGIRSE"
    echo ""
    echo "Soluciones sugeridas:"
    if [ $ERRORES -gt 0 ]; then
        echo "  • Ejecutar: sudo bash crear_usuario_cajero.sh"
        echo "  • Verificar permisos de archivos"
        echo "  • Revisar logs del sistema"
    fi
fi

echo ""
echo "Para más información, consultar:"
echo "  cat USUARIO_CAJERO_README.md"
echo ""

exit $ERRORES
