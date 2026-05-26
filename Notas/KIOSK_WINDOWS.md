# Modo Kiosk en Windows 11 (Mini PC)

Guía para dejar un equipo Windows 11 dedicado solo a la expendedora, equivalente al modo **cajero** de Raspberry Pi.

## Qué hace el instalador

El script `configSO/windows/install_cajero_kiosk.ps1` (como **Administrador**):

1. Crea el usuario local `cajero` (sin privilegios de administrador).
2. Configura **inicio de sesión automático** al arrancar.
3. Instala un **launcher** que ejecuta `main.py` en bucle (si se cierra, vuelve a abrir).
4. Opcionalmente reemplaza el **shell** de Windows (`explorer`) por el launcher (modo kiosk estricto).
5. Registra una **tarea programada** al iniciar sesión como respaldo.
6. Aplica **restricciones** básicas (sin Win, sin Administrador de tareas, etc.).
7. Evita suspensión de pantalla/standby en corriente alterna.

La GUI de la expendedora ya fuerza pantalla completa (`_apply_kiosk_window` en `expendedora_gui.py`).

## Requisitos

- Windows 11 Pro o Home (Mini PC).
- PowerShell 5.1 o superior.
- Python 3 instalado (`py -3` o `python` en PATH).
- Repositorio clonado en disco local (ej. `C:\Expendedora`).

## Instalación rápida

1. Abrí **PowerShell como administrador**.
2. Navegá al repositorio:

```powershell
cd C:\ruta\al\repo\expendedoraExperimental
```

3. Ejecutá el instalador:

```powershell
powershell -ExecutionPolicy Bypass -File .\configSO\windows\install_cajero_kiosk.ps1
```

Parámetros útiles:

```powershell
powershell -ExecutionPolicy Bypass -File .\configSO\windows\install_cajero_kiosk.ps1 `
  -KioskUser cajero `
  -Password 'TuClaveSegura123!' `
  -AppPath 'C:\Expendedora' `
  -LaunchMode Both
```

`-LaunchMode`:
- `Shell` — solo shell personalizado (kiosk estricto, sin escritorio).
- `Startup` — solo carpeta Inicio (más permisivo, ves barra de tareas brevemente).
- `Both` — recomendado en producción.

4. **Cambiá la contraseña** del usuario cajero y volvé a ejecutar el script (o actualizá `DefaultPassword` en el registro).
5. **Reiniciá** el equipo.

```powershell
shutdown /r /t 0
```

## Verificación

```powershell
powershell -ExecutionPolicy Bypass -File .\configSO\windows\verify_cajero_kiosk.ps1
```

Revisá el log del launcher:

```
C:\Users\cajero\expendedora-kiosk.log
```

## Actualizaciones automáticas

Igual que en Linux, registrá la tarea del updater:

```powershell
powershell -ExecutionPolicy Bypass -File .\updater\windows\register_updater_task.ps1
```

En `config.json`, podés definir reinicio tras update:

```json
"restart_command_windows": "taskkill /IM python.exe /F & timeout /t 2"
```

El launcher volverá a levantar `main.py` solo.

## Salir del modo kiosk (soporte técnico)

- `Ctrl+Alt+Supr` → **Cambiar usuario** e iniciá sesión como administrador.
- O ejecutá desinstalación:

```powershell
powershell -ExecutionPolicy Bypass -File .\configSO\windows\uninstall_cajero_kiosk.ps1
```

Para eliminar también el usuario:

```powershell
powershell -ExecutionPolicy Bypass -File .\configSO\windows\uninstall_cajero_kiosk.ps1 -RemoveUser
```

## Seguridad

| Aspecto | Detalle |
|--------|---------|
| Contraseña en registro | Auto-login guarda `DefaultPassword` en texto claro (limitación de Winlogon). Cambiá la clave y re-ejecutá install. |
| Usuario cajero | Nunca debe ser administrador. |
| Red | Mantené firewall y solo los puertos necesarios (MySQL/API). |
| BitLocker | Recomendado en equipos en campo. |

## Assigned Access (alternativa Microsoft)

Windows 11 ofrece **Acceso asignado** desde *Configuración → Cuentas → Otros usuarios → Configurar un quiosco*. Esa vía está pensada para una única app UWP/Store. Para **Python + Tkinter**, el enfoque de este repo (shell/launcher + pantalla completa) es el más práctico en Mini PC.

## Solución de problemas

### Pantalla negra tras reiniciar

El shell personalizado falló. Desde otro usuario admin:

```powershell
# Restaurar explorer para el usuario cajero (ver uninstall) o:
powershell -ExecutionPolicy Bypass -File .\configSO\windows\uninstall_cajero_kiosk.ps1
```

### La app no arranca

- Verificá Python: `py -3 --version`
- Probá manual como cajero: `py -3 C:\Expendedora\main.py`
- Revisá `C:\Users\cajero\expendedora-kiosk.log`

### Auto-login no funciona

- Ejecutá de nuevo `install_cajero_kiosk.ps1` como administrador.
- En algunas ediciones Home, desactivá “Exigir inicio de sesión” en `netplwiz` si interfiere.

### Permisos en `config.json` / `registro.json`

El instalador concede permisos de modificación en `AppPath` al usuario cajero. Si movés el repo, re-ejecutá install con `-AppPath` correcto.

---

**Relacionado:** `Notas/USUARIO_CAJERO_README.md` (Linux/Raspberry), `configSO/install_cajero_kiosk.sh`
