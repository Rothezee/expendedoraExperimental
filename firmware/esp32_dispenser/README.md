# Firmware — Arduino Uno

Control del motor y sensor óptico. Comunicación con la PC por **USB nativo** (115200 baud, JSON por línea).

**Archivos:** `esp32_dispenser.ino` + `config.h` — flashear con **Arduino IDE**.

## Cableado (tolva 1)

| Pin Arduino | Función |
|-------------|---------|
| **10** (D10) | Motor adelante → IN relé 1 |
| **12** (D12) | Motor atrás / reversa → IN relé 2 |
| **9** (D9) | Sensor óptico (`INPUT` si `sensor_blocked_high`, si no `INPUT_PULLUP`) |
| **GND** | Tierra común con relés y fuente del motor |

**Nota:** Los nombres internos del `.ino` están en español (`fichasRestantes`, `ejecutarDestrabe`, etc.). El protocolo JSON sigue en inglés (`TOKEN`, `SET_TARGET`, …).

### Destrabe automático

En `config.json` → `maquina.destrabe`:

- `max_intentos`: **3** (retrocesos automáticos por timeout antes de `JAM`)
- `retroceso_s`, `cooldown_s`, `auto_on_timeout`, `enabled`

Tras el JAM, el cajero usa el botón **Destrabar** en la GUI (`UNJAM` manual, sin límite).

No alimentar el motor desde el Arduino. Usar relés + fuente aparte.

### Relés (active-LOW)

En `config.json`: `"motor_active_low": true`.

El firmware **no enciende el motor** hasta recibir `CONFIG` desde la PC (al enchufar deja relés apagados).

---

## Arduino IDE

1. Instalar [Arduino IDE 2.x](https://www.arduino.cc/en/software).
2. **Administrador de bibliotecas** → **ArduinoJson** v7 (Benoit Blanchon).
3. **Archivo → Abrir** → carpeta `firmware/esp32_dispenser`.
4. **Herramientas → Placa:** `Arduino Uno`.
5. **Herramientas → Puerto:** COM del Uno (Administrador de dispositivos).
6. Cerrar `main.py` y monitor serial antes de **Subir**.

Velocidad de carga: **115200** (por defecto en Uno).

---

## Monitor serie

**Herramientas → Monitor serie** @ **115200**.

Prueba manual:

```json
{"dir":"cmd","type":"HELLO","v":1}
{"dir":"cmd","type":"CONFIG","hopper":{"id":1,"motor_pin":10,"motor_pin_rev":12,"motor_active_low":true,"sensor_pin":9,"sensor_bouncetime_ms":8,"calibracion":{"pulso_min_s":0.05,"pulso_max_s":0.5,"timeout_motor_s":2.0}}}
{"dir":"cmd","type":"SET_TARGET","remaining":3}
```

Desde PC:

```powershell
cd firmware\esp32_dispenser
python scripts\probe_hello.py COM3
```

(Reemplazar `COM3` por tu puerto Uno.)

---

## Config PC (`config.json`)

```json
"hardware": {
  "backend": "esp32_serial",
  "esp32": {
    "port": "",
    "baud": 115200,
    "auto_detect": true
  }
},
"maquina": {
  "hoppers": [{
    "motor_pin": 10,
    "motor_pin_rev": 12,
    "sensor_pin": 9,
    "motor_active_low": true
  }]
}
```

Tras cambiar el `.ino`, volver a **Subir**. Cambiar solo pines en `config.json` no requiere reflashear.

---

## Modo prueba (botón / LED)

En `config.h`: `#define TEST_STANDALONE 1` para probar sin PC (ver comentarios en el archivo).

---

## Protocolo

Ver `expendedora/logic/hardware/protocol.py`.

Comandos: `HELLO`, `CONFIG`, `SET_TARGET`, `SELECT_HOPPER`, `UNJAM`, `STOP`, `SIMULATE`, `PING`.

Eventos: `READY`, `TOKEN`, `MOTOR_ON`, `MOTOR_OFF`, `RUN_DONE`, `JAM`, `UNJAM_DONE`, `SYNC`, `ERR`.
