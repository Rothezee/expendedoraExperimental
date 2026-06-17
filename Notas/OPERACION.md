# Operación — PC + Arduino Uno

## Arquitectura

- **PC (Windows):** `python main.py` — GUI, MySQL, telemetría.
- **Arduino Uno (USB):** motor adelante pin **10**, reversa pin **12**, sensor pin **9**, timeout y destrabe.

## Instalación

```powershell
pip install -r requirements.txt
```

Credenciales MySQL (no commitear): copiar `expendedora/persistence/json/config.local.json.example` → `config.local.json` y poner la contraseña de `root`.

Flashear firmware: `firmware/esp32_dispenser/README.md` (Arduino IDE, placa **Arduino Uno**).

## Config (`expendedora/persistence/json/config.json`)

```json
"hardware": {
  "backend": "esp32_serial",
  "esp32": { "port": "", "baud": 115200, "auto_detect": true }
}
```

> La clave `esp32` en config es histórica; el hardware es **Arduino Uno** por USB.

Tolva 1 (fuente única: `expendedora/persistence/json/config.json`): `motor_pin` 10, `motor_pin_rev` 12, `sensor_pin` 9, `motor_active_low` true.

## Problemas frecuentes

| Síntoma | Qué hacer |
|---------|-----------|
| Sin conexión serial | Cerrar monitor serial; revisar COM del Uno en Administrador de dispositivos |
| No dispensa | Relés, `motor_active_low`, pines en config |
| Relé hace clic pero motor no gira | Ver sección **Relé OK, motor quieto** abajo |
| Sensor no cuenta | Pin 8 + GND; ver sección **Sensor óptico**; reflashear firmware |
| JAM / timeout | Sensor en pin 9; subir `timeout_motor_s` en calibración |
| Upload falla | Otro puerto COM ocupado; cable USB data (no solo carga) |

## Calibración

Editar en `expendedora/persistence/json/config.json` → `maquina.hoppers[].calibracion`:

- `pulso_min_s`, `pulso_max_s` — duración del pulso del sensor
- `timeout_motor_s` — máximo sin ficha antes de JAM

Reiniciar `main.py` para enviar CONFIG al Arduino.

## Persistencia de contadores (cortes de luz)

- **Archivo canónico:** `expendedora/persistence/json/machine_state.json` (escritura atómica en cada evento crítico: moneda, promo, ficha dispensada, cierre).
- **Copia en** `expendedora/persistence/json/config.json` → sección `contadores` (sincronizada al persistir).
- **Legacy (solo migración al arrancar):** `buffer_state.json`, `registro.json` (se copian desde ubicaciones anteriores al primer arranque).
- Tras un corte inesperado: volver a ejecutar `python main.py`. En consola buscar `[STATE] Recuperado desde: ...`.
- Cierre normal de la app: guarda estado en `shutdown` vía `_persistir_estado_critico`.
- Backup automático: `expendedora/persistence/json/machine_state.json.bak` (última versión válida antes de cada escritura).

## Motor / sensor (Arduino)

- Al conectar USB el motor **no debe arrancar solo**: solo gira después de cargar fichas en la GUI (Expender / promo) y enviar `SET_TARGET`.
- Relés de módulo suelen ser **active-LOW**: `"motor_active_low": true` (HIGH en pin = apagado).
- Pin **10** (motor) no es el LED integrado; el pin 13 del Uno tiene LED onboard — no confundir cableado de relés.
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

Reiniciar `python main.py`. En consola: `[DBG MOTOR]`, `[DBG SENSOR]`, `[DBG PC→ARDUINO]`.

En el Arduino: `#define DEBUG_SENSOR 1` en `config.h` + **Monitor serie** @ 115200 (cerrar `main.py` antes).

## Relé OK, motor quieto

Si el **módulo de relés hace clic** pero el **motor no gira**, el Arduino suele estar bien; revisar el **circuito de potencia**:

1. **Fuente del motor aparte** — el Arduino solo acciona el relé (5 V lógica). El motor necesita su propia fuente (12 V / 24 V según tolva).
2. **COM / NO / NC** — la fuente del motor debe pasar por **COM** y **NO** (contacto normalmente abierto). Si usás NC, el motor queda apagado cuando el relé se activa.
3. **`motor_active_low`** — módulos típicos: LOW en IN = relé ON. Si tu módulo es al revés, probá `"motor_active_low": false` en config.
4. **Un solo relé a la vez** — adelante pin **10**, reversa pin **12**. Si ambos relés suenan juntos, revisar cableado cruzado.
5. **Continuidad** — con relé activado, medir tensión **en bornes del motor** (no solo en la bobina del relé).

## Sensor óptico (pin 9)

Config en `maquina.hoppers[]`:

- **`sensor_blocked_high`: true** (default en esta máquina) — **libre = 0 (LOW)**, **tapado/cortado = 1 (HIGH)**. Pin en modo `INPUT` (sin pull-up interno).
- **`sensor_blocked_high`: false** — reposo HIGH (`INPUT_PULLUP`), haz cortado = LOW (sensor tipo NPN común).

El firmware cuenta 1 ficha por pulso completo: **0→1** (entra ficha) y **1→0** (sale) = TOKEN.

Prueba manual (monitor serial @ 115200, `DEBUG_SENSOR 1` en `config.h`):

- Con el haz **libre**: `raw=LOW(0)`.
- Tapando el haz: `raw=HIGH(1)`, flanco `0->1` = inicio de pulso.
- Al liberar: flanco `1->0` y `TOKEN`.
- Tras CONFIG debe verse `blocked_high=1`. Si ves `blocked_high=0`, el Arduino sigue con la lógica invertida.
- Si el pin queda siempre HIGH o siempre LOW: revisar cable señal + GND común y alimentación del emisor/receptor del sensor.

## Checklist en campo (antes de release)

Con Arduino conectado y monitor serial **cerrado**:

| # | Prueba | Esperado |
|---|--------|----------|
| 1 | `python main.py` | Login OK; `[ARDUINO] READY` o reconexión sin crash |
| 2 | Dispensar 1 ficha | 1 TOKEN, pendientes → 0, contador sesión +1 |
| 3 | Dispensar 2 / 5 / 10 fichas | Conteo 1:1 con sensor |
| 4 | Fin de tanda | `[NET] telemetria` sin 403 (requiere `codigo_hardware` en config) |
| 5 | Logout | Sesión resetea; global de fichas se conserva |
| 6 | Corte simulado | Matar app mid-dispense; reiniciar → `[STATE] Recuperado desde: ...` |
| 7 | JAM / destrabe | Timeout → hasta 3 destrabes auto; luego JAM; botón Destrabar → `UNJAM_DONE` |

Detalle: skill `expendedora-field-validation` en `.cursor/skills/`.
