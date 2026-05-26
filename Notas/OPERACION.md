# Operación — PC + Arduino Uno

## Arquitectura

- **PC (Windows):** `python main.py` — GUI, MySQL, telemetría.
- **Arduino Uno (USB):** motor adelante pin **13**, reversa pin **11**, sensor pin **9**, timeout y destrabe.

## Instalación

```powershell
pip install -r requirements.txt
```

Flashear firmware: `firmware/esp32_dispenser/README.md` (Arduino IDE, placa **Arduino Uno**).

## Config (`config.json`)

```json
"hardware": {
  "backend": "esp32_serial",
  "esp32": { "port": "", "baud": 115200, "auto_detect": true }
}
```

Tolva 1: `motor_pin` 13, `motor_pin_rev` 11, `sensor_pin` 9, `motor_active_low` true.

## Problemas frecuentes

| Síntoma | Qué hacer |
|---------|-----------|
| Sin conexión serial | Cerrar monitor serial; revisar COM del Uno en Administrador de dispositivos |
| No dispensa | Relés, `motor_active_low`, pines en config |
| JAM / timeout | Sensor en pin 9; subir `timeout_motor_s` en calibración |
| Upload falla | Otro puerto COM ocupado; cable USB data (no solo carga) |

## Calibración

Editar en `config.json` → `maquina.hoppers[].calibracion`:

- `pulso_min_s`, `pulso_max_s` — duración del pulso del sensor
- `timeout_motor_s` — máximo sin ficha antes de JAM

Reiniciar `main.py` para enviar CONFIG al Arduino.

## Persistencia de contadores (cortes de luz)

- **Archivo canónico:** `machine_state.json` (escritura atómica en cada evento crítico: moneda, promo, ficha dispensada, cierre).
- **Copia en** `config.json` → sección `contadores` (sincronizada al persistir).
- **Legacy (solo migración al arrancar):** `buffer_state.json`, `registro.json`.
- Tras un corte inesperado: volver a ejecutar `python main.py`. En consola buscar `[STATE] Recuperado desde: ...`.
- Cierre normal de la app: guarda estado en `shutdown` vía `_persistir_estado_critico`.
- Backup automático: `machine_state.json.bak` (última versión válida antes de cada escritura).

## Motor / sensor (Arduino)

- Al conectar USB el motor **no debe arrancar solo**: solo gira después de cargar fichas en la GUI (Expender / promo) y enviar `SET_TARGET`.
- Relés de módulo suelen ser **active-LOW**: `"motor_active_low": true` (HIGH en pin = apagado).
- Pin **13** comparte LED del Uno; no usar ese LED como indicador fiable con relés cableados.
- Si **descuenta todas las fichas de golpe**: rebote del sensor; subir `pulso_min_s` (ej. 0.15–0.3 s).
- Tras cambios en `esp32_dispenser.ino`, reflashear con **Arduino IDE** (Subir).

## Debug motor / sensor

Activar en `config.json`:

```json
"hardware": {
  "esp32": {
    "debug_motor_sensor": true
  }
}
```

Reiniciar `python main.py`. En consola: `[DBG MOTOR]`, `[DBG SENSOR]`, `[DBG PC→ESP32]`.

En el Arduino: `#define DEBUG_SENSOR 1` en `config.h` + **Monitor serie** @ 115200 (cerrar `main.py` antes).
