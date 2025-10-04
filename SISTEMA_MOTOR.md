# Sistema de Control de Motor Basado en Fichas Restantes

## Descripción General

El motor se controla automáticamente basándose en el contador `fichas_restantes`:
- **Motor ENCENDIDO**: cuando `fichas_restantes > 0`
- **Motor APAGADO**: cuando `fichas_restantes == 0`

El sensor del hopper (ENTHOPER) cuenta las fichas que salen y decrementa automáticamente el contador.

## ⚠️ IMPORTANTE: Sincronización Hardware-GUI

El core (hardware) siempre inicia con `fichas_restantes = 0` y `fichas_expendidas = 0`.

La GUI debe sincronizarse con estos valores al iniciar para evitar que el motor quede encendido indefinidamente.

**Problema común**: Si la GUI guarda y restaura `fichas_restantes` de sesiones anteriores pero el hardware inicia en 0, se produce una desincronización que causa que el motor nunca se encienda o nunca se apague correctamente.

**Solución implementada**: Al cargar la configuración, siempre resetear los contadores de fichas:
```python
self.contadores["fichas_restantes"] = 0
self.contadores["fichas_expendidas"] = 0
```

## Flujo de Operación

### 1. Usuario Agrega Fichas
```python
# Desde la GUI o promociones
core.agregar_fichas(5)
```
- Se incrementa `fichas_restantes`
- El hilo de control detecta `fichas_restantes > 0`
- **El motor se ENCIENDE automáticamente**

### 2. Fichas Salen del Hopper
```
Sensor ENTHOPER detecta:
HIGH -> LOW (flanco descendente)
```
- Se decrementa `fichas_restantes` automáticamente
- Se incrementa `fichas_expendidas`
- Se actualiza el registro

### 3. Motor se Apaga Automáticamente
```
Cuando fichas_restantes llega a 0:
```
- El hilo de control detecta `fichas_restantes == 0`
- **El motor se APAGA automáticamente**

## Componentes Clave

### expendedora_core.py
```python
# Variables globales
fichas_restantes = 0    # Fichas pendientes por expender
fichas_expendidas = 0   # Total de fichas expendidas
motor_activo = False    # Estado del motor

# Hilo principal
def controlar_motor():
    while True:
        # Activar motor si hay fichas
        if fichas_restantes > 0 and not motor_activo:
            GPIO.output(MOTOR_PIN, GPIO.HIGH)
            motor_activo = True

        # Apagar motor si no hay fichas
        elif fichas_restantes <= 0 and motor_activo:
            GPIO.output(MOTOR_PIN, GPIO.LOW)
            motor_activo = False

        # Detectar fichas que salen
        if sensor_detecta_flanco_descendente():
            fichas_restantes -= 1
            fichas_expendidas += 1
```

### expendedora_gui.py
```python
# La GUI se actualiza desde el hardware cada 500ms
def actualizar_desde_hardware(self):
    fichas_restantes_hw = core.obtener_fichas_restantes()
    fichas_expendidas_hw = core.obtener_fichas_expendidas()

    # Actualizar contadores en la GUI
    self.contadores["fichas_restantes"] = fichas_restantes_hw
    self.contadores["fichas_expendidas"] = fichas_expendidas_hw

    # Programar próxima actualización en 500ms
    self.root.after(500, self.actualizar_desde_hardware)
```

## Funciones Disponibles

### Agregar Fichas
```python
core.agregar_fichas(cantidad)
# Activa el motor automáticamente si hay fichas pendientes
```

### Consultar Estado
```python
fichas_pendientes = core.obtener_fichas_restantes()
fichas_total = core.obtener_fichas_expendidas()
motor_encendido = core.motor_activo
```

### Simular Sensor (para pruebas)
```python
from gpio_sim import GPIO
GPIO.simulate_sensor_pulse(core.ENTHOPER)
# Simula una ficha saliendo del hopper
```

## Características

✅ **Control Automático del Motor**: No es necesario encender/apagar manualmente
✅ **Conteo Preciso con Anti-Rebote**: El sensor cuenta cada ficha sin duplicados
✅ **Actualización en Tiempo Real**: La GUI se actualiza cada 500ms
✅ **Thread-Safe**: Usa locks para evitar condiciones de carrera
✅ **Detección de Flancos con Debounce**: Ignora rebotes del sensor (300ms)
✅ **Sistema de Promociones**: Las promociones activan el motor automáticamente

## Ejemplo de Uso

```python
# Paso 1: Usuario compra 5 fichas
core.agregar_fichas(5)
# Motor se enciende automáticamente

# Paso 2: Las fichas van saliendo
# Sensor cuenta: 5 -> 4 -> 3 -> 2 -> 1 -> 0

# Paso 3: Motor se apaga cuando llega a 0
# El sistema está listo para la próxima compra
```

## Configuración de Hardware

```python
MOTOR_PIN = 24       # Pin GPIO del motor
ENTHOPER = 23        # Pin GPIO del sensor del hopper
PULSO_MIN = 0.05     # 50ms - Duración mínima del pulso (filtro de ruido)
PULSO_MAX = 0.5      # 500ms - Duración máxima del pulso (detección de atascos)

# Sensor configurado con pull-up
# Estado normal: HIGH
# Ficha detectada: LOW -> HIGH (pulso completo)
```

### Detección de Pulso Completo

El sistema detecta un **pulso completo** en lugar de solo flancos:

```
HIGH (sin ficha) → LOW (ficha bloquea) → HIGH (ficha pasó)
         |              [50-500ms]            |
         +--------- Solo aquí se cuenta ------+
```

**Ventajas:**
- ✅ Independiente de la velocidad del motor
- ✅ Elimina rebotes automáticamente
- ✅ Filtra ruido eléctrico (< 50ms)
- ✅ Detecta atascos (> 500ms)

**Ver `CONFIGURACION_SENSOR.md` para ajustes detallados**

## Ventajas del Sistema

1. **Totalmente Automático**: El operador solo agrega fichas, el motor se controla solo
2. **Preciso**: Cuenta exactamente las fichas que salen
3. **Eficiente**: Solo gasta energía cuando hay fichas pendientes
4. **Seguro**: Usa locks para operaciones thread-safe
5. **Fácil de Mantener**: Lógica clara y separada por responsabilidades
