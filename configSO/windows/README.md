# Kiosk Windows 11

Scripts para Mini PC con Windows 11.

| Script | Uso |
|--------|-----|
| `install_cajero_kiosk.ps1` | Instalación completa (admin) |
| `uninstall_cajero_kiosk.ps1` | Revertir kiosk |
| `verify_cajero_kiosk.ps1` | Comprobar configuración |
| `apply_kiosk_restrictions.ps1` | Uso interno (restricciones registro) |

Documentación detallada: [Notas/KIOSK_WINDOWS.md](../../Notas/KIOSK_WINDOWS.md)

```powershell
powershell -ExecutionPolicy Bypass -File .\configSO\windows\install_cajero_kiosk.ps1
```
