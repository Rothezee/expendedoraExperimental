# Configuración del Sensor de Fichas

## Método de Detección: Pulso Completo

El sistema ahora utiliza **detección de pulso completo** en lugar de solo flancos descendentes.

### ¿Cómo funciona?

```
Estado del sensor:

  HIGH (sin ficha)
    |
    v
  LOW (ficha bloquea el sensor)  <-- Ficha detectada entrando
    |
    | [Duración del pulso: 50ms - 500ms]
    |
    v
  HIGH (ficha pasó)  <-- Ficha contada aquí
```

### Ventajas

✅ **Elimina rebotes**: Solo cuenta cuando el pulso es completo (HIGH->LOW->HIGH)
✅ **Más preciso**: Ignora ruido eléctrico (pulsos < 50ms)
✅ **Detecta atascos**: Identifica fichas bloqueadas (pulsos > 500ms)
✅ **Sin falsos positivos**: No cuenta mientras la ficha sigue en el sensor

## Configuración de Tiempos

```python
# En expendedora_core.py

PULSO_MIN = 0.05  # 50ms - Duración mínima válida del pulso
PULSO_MAX = 0.5   # 500ms - Duración máxima válida del pulso
```

### Ajuste según tu hardware:

#### Si las fichas NO se cuentan (expendidas < esperadas):
- **Problema**: El pulso es muy corto o muy largo
- **Revisar logs**: Buscar `[RUIDO IGNORADO]` o `[ADVERTENCIA] Pulso muy largo`
- **Solución**:
  - Si hay ruido: AUMENTAR `PULSO_MIN` a 0.08 (80ms)
  - Si hay bloqueos: AUMENTAR `PULSO_MAX` a 0.8 (800ms)

#### Si las fichas se cuentan múltiples veces (expendidas > esperadas):
- **Problema**: Esto NO debería ocurrir con detección de pulso completo
- **Verificar**:
  - Que el sensor tenga pull-up (debe estar en HIGH cuando no hay ficha)
  - Que las fichas pasen completamente por el sensor
  - Conexión del sensor correcta

## Logs de Diagnóstico

### Funcionamiento Normal:
```
[MOTOR ON] Fichas pendientes: 5
[SENSOR] Ficha detectada entrando...
[FICHA EXPENDIDA] Restantes: 4 | Total: 1 | Duración: 120.5ms
[SENSOR] Ficha detectada entrando...
[FICHA EXPENDIDA] Restantes: 3 | Total: 2 | Duración: 115.2ms
...
[MOTOR OFF] Todas las fichas expendidas
```

### Ruido Eléctrico:
```
[SENSOR] Ficha detectada entrando...
[RUIDO IGNORADO] Pulso muy corto: 15.3ms
```
**Solución**: Aumentar `PULSO_MIN`

### Ficha Atascada:
```
[SENSOR] Ficha detectada entrando...
[ADVERTENCIA] Pulso muy largo: 850.2ms
```
**Solución**: Revisar hardware o aumentar `PULSO_MAX` si es normal

### Sensor Desconectado:
```
[MOTOR ON] Fichas pendientes: 5
(No aparece "[SENSOR] Ficha detectada entrando...")
```
**Solución**: Verificar conexión del sensor y pull-up

## Velocidad de Polling

```python
time.sleep(0.005)  # 5ms de polling
```

**Frecuencia**: 200 lecturas por segundo

### Ajustar si es necesario:
- **Hardware lento**: Aumentar a 0.01 (100 lecturas/seg)
- **Hardware rápido**: Mantener en 0.005 o reducir a 0.003

## Prueba de Calibración

1. Agregar exactamente 10 fichas
2. Esperar a que todas salgan
3. Verificar el contador:
   - **Correcto**: 10 fichas expendidas
   - **Menos de 10**: Ajustar tiempos de pulso
   - **Más de 10**: Verificar hardware del sensor

## Comparación: Antes vs Ahora

### Método Anterior (Anti-rebote por tiempo)
```python
# Problema: Si el motor iba rápido, contaba múltiples veces
if flanco_descendente and tiempo_desde_ultimo > 0.3:
    contar_ficha()
```
❌ Dependía de calibrar el tiempo exacto
❌ Si el motor cambiaba velocidad, fallaba

### Método Actual (Pulso completo)
```python
# Espera a que la ficha pase completamente
if pulso_completo and duracion_valida:
    contar_ficha()
```
✅ Independiente de la velocidad del motor
✅ Solo cuenta cuando la ficha pasó completamente
✅ Filtra ruido automáticamente

## Compatibilidad con Hardware Real

### Para Raspberry Pi:
```python
# En expendedora_core.py línea 2
import RPi.GPIO as GPIO  # Descomentar esta línea

# Y comentar:
# from gpio_sim import GPIO
```

### Configuración del Pin:
```python
GPIO.setup(ENTHOPER, GPIO.IN, pull_up_down=GPIO.PUD_UP)
```

El sensor debe estar conectado de manera que:
- **Sin ficha**: Pin en HIGH (3.3V)
- **Con ficha**: Pin en LOW (0V - GND)

## Resumen

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `MOTOR_PIN` | 24 | Pin GPIO del motor |
| `ENTHOPER` | 23 | Pin GPIO del sensor |
| `PULSO_MIN` | 0.05s (50ms) | Filtro de ruido |
| `PULSO_MAX` | 0.5s (500ms) | Detección de atascos |
| Polling | 0.005s (5ms) | Velocidad de lectura |

✅ Sistema probado y funcionando correctamente
✅ No requiere calibración de velocidad del motor
✅ Filtrado automático de rebotes y ruido
