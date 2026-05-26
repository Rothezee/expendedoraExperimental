# Expendedora de fichas — PC + Arduino Uno

Sistema de caja en **Windows** con dispensado por **Arduino Uno** (USB serial).

## Stack

| Componente | Rol |
|------------|-----|
| `main.py` / `expendedora_gui.py` | Operación, promos, cierres, MySQL |
| `expendedora_core.py` / `infra/esp32_bridge.py` | Puente serial |
| `firmware/esp32_dispenser/` | Sketch Uno — pines 13 / 11 / 9 |

## Inicio rápido

```powershell
pip install -r requirements.txt
# Flashear Arduino Uno: firmware/esp32_dispenser/README.md
python main.py
```

Header de la app: **ESP32: OK** (verde) = conexión serial lista (el label es legacy; funciona con Uno).

## Configuración

`config.json`:

- `hardware.esp32` — puerto COM del Arduino (`""` + `auto_detect: true` recomendado)
- `maquina.hoppers[]` — pines y calibración por tolva

## Documentación

- [Notas/OPERACION.md](Notas/OPERACION.md) — operación y fallas frecuentes
- [firmware/esp32_dispenser/README.md](firmware/esp32_dispenser/README.md) — cableado y flasheo

## Estructura

```
├── main.py, expendedora_gui.py, expendedora_core.py
├── config.json, shared_buffer.py
├── firmware/esp32_dispenser/
├── infra/          # esp32_serial_client, protocol, MySQL, telemetría
├── services/
├── tests/
├── updater/        # actualización git (Windows)
└── User_management/
```

## Actualizador (opcional)

```powershell
powershell -ExecutionPolicy Bypass -File updater/run_update_windows.ps1
```
