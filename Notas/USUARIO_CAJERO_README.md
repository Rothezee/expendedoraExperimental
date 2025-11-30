# Configuración de Usuario Cajero (Modo Kiosk)

Este sistema crea un usuario "cajero" con acceso restringido tipo kiosk para operar la expendedora de forma segura.

## Características del Usuario Cajero

### ✅ Acceso Permitido
- Ejecutar la aplicación expendedora
- Ver la interfaz gráfica
- Cerrar sesión
- Operaciones básicas de la expendedora

### ❌ Acceso Restringido
- No puede abrir terminal
- No puede instalar software
- No tiene acceso a sudo
- No puede modificar archivos del sistema
- No puede acceder a otros directorios
- Teclas de acceso directo bloqueadas

## Instalación

### Paso 1: Crear el usuario cajero

```bash
sudo bash crear_usuario_cajero.sh
```

Este script:
- Crea el usuario "cajero" con contraseña predeterminada
- Configura auto-login al iniciar la Raspberry Pi
- Crea acceso directo en el escritorio
- Configura inicio automático de la aplicación
- Bloquea la barra de tareas
- Da permisos necesarios para GPIO y bases de datos

### Paso 2: Aplicar restricciones adicionales (Opcional pero recomendado)

```bash
sudo bash restricciones_cajero.sh
```

Este script:
- Bloquea acceso a terminal (Ctrl+Alt+T)
- Deshabilita teclas de acceso directo peligrosas
- Restringe comandos del sistema (rm, mv, sudo, etc.)
- Configura auto-bloqueo después de 10 minutos
- Limita navegación por el sistema de archivos

### Paso 3: Cambiar la contraseña (MUY IMPORTANTE)

```bash
sudo passwd cajero
```

La contraseña predeterminada es `cajero123` - **CÁMBIALA INMEDIATAMENTE**

### Paso 4: Reiniciar

```bash
sudo reboot
```

## Uso

### Inicio Automático

Cuando la Raspberry Pi se enciende:
1. El sistema hace login automáticamente como "cajero"
2. Se inicia el escritorio
3. La aplicación expendedora se abre automáticamente
4. El cajero puede empezar a trabajar de inmediato

### Operación Manual

Si el cajero cierra la aplicación, puede reiniciarla:
- **Desde escritorio**: Doble clic en "Sistema Expendedora"
- **Desde terminal** (si está habilitado): Escribir `iniciar`

### Cerrar Sesión

Para cerrar sesión del usuario cajero:
- Menú de inicio → Logout
- O desde terminal: `salir`

## Estructura de Archivos

```
/home/admin/expendedoraExperimental/     # Aplicación (solo lectura para cajero)
├── main.py
├── expendedora_core.py
├── expendedora_gui.py
├── expendedora.db                       # Base de datos (lectura/escritura)
├── users.db                             # Base de datos usuarios
└── registro.json                        # Registro de operaciones

/home/cajero/                            # Directorio del cajero
├── Desktop/
│   └── Expendedora.desktop              # Acceso directo
├── .config/
│   ├── autostart/
│   │   ├── expendedora.desktop          # Auto-inicio aplicación
│   │   └── autolock.desktop             # Auto-bloqueo
│   ├── lxpanel/                         # Configuración panel
│   └── openbox/                         # Configuración ventanas
├── .bashrc                              # Bash restringido
└── .profile                             # Perfil limitado
```

## Seguridad

### Niveles de Seguridad Implementados

1. **Usuario sin privilegios**: No tiene acceso sudo ni root
2. **Acceso a archivos limitado**: Solo puede leer la aplicación, no modificarla
3. **Comandos bloqueados**: No puede ejecutar comandos peligrosos
4. **Terminal deshabilitado**: No puede abrir shells alternativos
5. **Auto-bloqueo**: Pantalla se bloquea tras 10 min de inactividad
6. **Modo kiosk**: Solo puede ejecutar la aplicación autorizada

### Recomendaciones Adicionales

- Cambiar la contraseña regularmente
- Monitorear logs del sistema: `/var/log/auth.log`
- Verificar permisos de archivos periódicamente
- Mantener el sistema actualizado

## Solución de Problemas

### La aplicación no inicia automáticamente

```bash
# Verificar archivo autostart
cat /home/cajero/.config/autostart/expendedora.desktop

# Verificar permisos
ls -la /home/admin/expendedoraExperimental/main.py

# Probar manualmente
sudo -u cajero python3 /home/admin/expendedoraExperimental/main.py
```

### El cajero puede acceder a cosas que no debería

```bash
# Re-aplicar restricciones
sudo bash restricciones_cajero.sh

# Verificar grupos del usuario
groups cajero

# Eliminar de grupos peligrosos
sudo deluser cajero sudo
sudo deluser cajero adm
```

### Error de permisos en base de datos

```bash
# Dar permisos a las bases de datos
sudo chmod 666 /home/admin/expendedoraExperimental/expendedora.db
sudo chmod 666 /home/admin/expendedoraExperimental/users.db
sudo chmod 666 /home/admin/expendedoraExperimental/registro.json
```

### El usuario no hace auto-login

```bash
# Verificar configuración de LightDM
cat /etc/lightdm/lightdm.conf | grep autologin

# Debe mostrar:
# autologin-user=cajero

# Si no, editar:
sudo nano /etc/lightdm/lightdm.conf
# Agregar o descomentar: autologin-user=cajero
```

### Bloqueo de pantalla no funciona

```bash
# Instalar xautolock si no está
sudo apt-get install xautolock

# Verificar que el script existe
ls -la /home/cajero/auto_lock.sh

# Probar manualmente
sudo -u cajero /home/cajero/auto_lock.sh
```

## Desinstalación

### Eliminar usuario cajero

```bash
# Eliminar usuario y su directorio
sudo userdel -r cajero

# Deshabilitar auto-login
sudo sed -i 's/^autologin-user=/#autologin-user=/' /etc/lightdm/lightdm.conf

# O restaurar backup
sudo cp /etc/lightdm/lightdm.conf.backup /etc/lightdm/lightdm.conf

# Reiniciar
sudo reboot
```

## Personalización

### Cambiar aplicación que se ejecuta

Editar:
```bash
sudo nano /home/cajero/.config/autostart/expendedora.desktop
```

Cambiar la línea `Exec=` por la aplicación deseada.

### Cambiar tiempo de auto-bloqueo

Editar:
```bash
sudo nano /home/cajero/auto_lock.sh
```

Cambiar `-time 10` por el tiempo deseado en minutos.

### Agregar más restricciones

El archivo `/home/cajero/.config/openbox/lxde-pi-rc.xml` controla las teclas bloqueadas.

### Permitir más comandos

Editar:
```bash
sudo nano /home/cajero/.bashrc
```

Comentar o eliminar los alias que bloquean comandos.

## Notas Importantes

⚠️ **ADVERTENCIAS**:
- El usuario cajero NO debe tener acceso a sudo bajo ninguna circunstancia
- Cambiar la contraseña predeterminada es OBLIGATORIO
- Los permisos de las bases de datos (666) permiten lectura/escritura a todos los usuarios - ajustar según necesidades de seguridad
- El auto-login es conveniente pero menos seguro - desactivar si no es necesario

✅ **MEJORES PRÁCTICAS**:
- Revisar logs regularmente
- Mantener backups de las bases de datos
- Probar el sistema en modo cajero antes de producción
- Documentar cualquier cambio adicional

## Soporte

Para problemas o preguntas:
1. Revisar los logs: `tail -f /var/log/syslog`
2. Verificar permisos de archivos
3. Probar desde el usuario admin primero
4. Consultar documentación de LXDE/Openbox/LightDM

---

**Creado para**: Sistema de Expendedora
**Versión**: 1.0
**Fecha**: 2025
**Plataforma**: Raspberry Pi OS (Debian)
