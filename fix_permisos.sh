#!/bin/bash
################################################################################
# Script para corregir el problema crítico de escritura
################################################################################

echo "=========================================="
echo "CORRECCIÓN DE PERMISOS DE ESCRITURA"
echo "=========================================="

if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: Ejecutar como root: sudo bash $0"
    exit 1
fi

USUARIO_CAJERO="cajero"
USUARIO_ADMIN="admin"
APP_PATH="/home/admin/expendedoraExperimental"

echo ""
echo "[1/4] Corrigiendo permisos del directorio principal..."

# El problema: el directorio no permite crear archivos al usuario cajero
# Solución: cambiar propietario a admin pero dar permisos de grupo completos

# Cambiar grupo del directorio a un grupo compartido
chgrp -R admin "$APP_PATH"

# Dar permisos completos al grupo
chmod -R g+rwx "$APP_PATH"

# Hacer que los archivos nuevos hereden el grupo
chmod g+s "$APP_PATH"

# Dar permisos de escritura al directorio principal
chmod 775 "$APP_PATH"

echo "✓ Permisos del directorio principal corregidos"

echo ""
echo "[2/4] Configurando ACLs para permitir escritura..."

# Dar permisos ACL recursivos al usuario cajero
setfacl -R -m u:$USUARIO_CAJERO:rwx "$APP_PATH" 2>/dev/null || {
    echo "⚠ setfacl no disponible, usando método alternativo..."
    # Método alternativo: hacer todo world-writable (menos seguro pero funcional)
    chmod -R 777 "$APP_PATH"
}

# Establecer ACL por defecto para archivos nuevos
setfacl -R -d -m u:$USUARIO_CAJERO:rwx "$APP_PATH" 2>/dev/null || true
setfacl -R -d -m g:admin:rwx "$APP_PATH" 2>/dev/null || true

echo "✓ ACLs configurados"

echo ""
echo "[3/4] Verificando permisos de carpetas críticas..."

# Asegurar que todas las subcarpetas sean escribibles
for dir in $(find "$APP_PATH" -type d); do
    chmod 777 "$dir"
done

# Asegurar subcarpetas específicas
for subdir in logs data temp cache sessions __pycache__ User_management .cache; do
    if [ -d "$APP_PATH/$subdir" ]; then
        chmod -R 777 "$APP_PATH/$subdir"
        echo "  ✓ $subdir - Permisos de escritura OK"
    fi
done

echo "✓ Carpetas críticas verificadas"

echo ""
echo "[4/4] Realizando prueba de escritura..."

# Crear script de prueba más exhaustivo
cat > /tmp/test_write.sh <<'EOF'
#!/bin/bash
APP_PATH="/home/admin/expendedoraExperimental"
cd "$APP_PATH" || exit 1

echo "=== PRUEBA DE ESCRITURA ==="
echo "Usuario: $(whoami)"
echo "Directorio: $(pwd)"
echo ""

# Prueba 1: Crear archivo en directorio principal
TEST_FILE="test_$(date +%s).tmp"
echo "1. Creando archivo en directorio principal..."
if echo "test" > "$TEST_FILE" 2>/dev/null; then
    echo "   ✓ Puede crear archivos en directorio principal"
    rm -f "$TEST_FILE"
else
    echo "   ✗ NO puede crear archivos en directorio principal"
    ls -ld "$APP_PATH"
fi

# Prueba 2: Crear archivo en subcarpetas
for dir in logs data temp cache sessions; do
    if [ -d "$dir" ]; then
        echo "2. Probando escritura en $dir/..."
        if touch "$dir/test.tmp" 2>/dev/null; then
            echo "   ✓ Puede escribir en $dir/"
            rm -f "$dir/test.tmp"
        else
            echo "   ✗ NO puede escribir en $dir/"
            ls -ld "$dir"
        fi
    fi
done

# Prueba 3: Permisos efectivos
echo ""
echo "3. Permisos efectivos del directorio:"
ls -la "$APP_PATH" | head -5

echo ""
echo "4. Grupos del usuario:"
groups

echo ""
echo "=== FIN DE PRUEBA ==="
EOF

chmod +x /tmp/test_write.sh

echo ""
echo "Ejecutando como usuario $USUARIO_CAJERO..."
echo "----------------------------------------"
su - "$USUARIO_CAJERO" -c "/tmp/test_write.sh"
echo "----------------------------------------"

rm -f /tmp/test_write.sh

echo ""
echo "=========================================="
echo "DIAGNÓSTICO ADICIONAL"
echo "=========================================="
echo ""
echo "Permisos del directorio principal:"
ls -ld "$APP_PATH"
echo ""
echo "Permisos de archivos clave:"
ls -l "$APP_PATH"/*.db "$APP_PATH"/*.json 2>/dev/null
echo ""

# Verificar ACLs si están disponibles
if command -v getfacl &> /dev/null; then
    echo "ACLs del directorio principal:"
    getfacl "$APP_PATH" 2>/dev/null | grep -E "user:|group:|other:"
fi

echo ""
echo "=========================================="
echo "INSTRUCCIONES FINALES"
echo "=========================================="
echo ""
echo "Si la prueba muestra que ahora puede escribir (✓):"
echo "  1. Prueba la aplicación: sudo su - cajero"
echo "  2. cd /home/admin/expendedoraExperimental"
echo "  3. python3 main.py"
echo ""
echo "Si aún no puede escribir (✗):"
echo "  1. Verifica el propietario: ls -ld $APP_PATH"
echo "  2. Verifica que cajero esté en grupo admin: groups cajero"
echo "  3. Considera mover la app a /opt/expendedora con permisos completos"
echo ""
