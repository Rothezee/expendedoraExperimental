# Solución de Problemas - Sistema de Motor

## Problema 1: El contador de fichas restantes no se actualiza en la GUI

### Síntomas
- El usuario agrega fichas
- Las fichas empiezan a salir
- El contador en pantalla no disminuye
- El motor sigue funcionando indefinidamente

### Causa
Desincronización entre el hardware (core) y la GUI. El core inicia siempre en 0, pero la GUI restaura valores guardados.

### Solución Implementada
1. La GUI resetea los contadores al cargar: `fichas_restantes = 0`
2. La función `actualizar_desde_hardware()` sincroniza cada 500ms
3. Los contadores se actualizan directamente desde el hardware

### Verificación
```python
# Al agregar fichas, verificar que:
print(f"Core: {core.obtener_fichas_restantes()}")
print(f"GUI: {self.contadores['fichas_restantes']}")
# Ambos deben ser iguales
```

## Problema 2: Salen más fichas de las esperadas (rebote del sensor)

### Síntomas
- Se agregan 3 fichas
- Salen 5 o más fichas
- El contador se decrementa más rápido de lo debido

### Causa
El sensor tiene "rebote" (bounce) - cuando una ficha pasa, el sensor puede detectar múltiples transiciones HIGH->LOW debido a:
- Vibraciones mecánicas
- Fichas que se mueven irregularmente
- Ruido eléctrico
- Motor muy rápido

### Solución Implementada: Anti-Rebote (Debounce)

#### Configuración
```python
# En expendedora_core.py
DEBOUNCE_TIME = 0.3  # Tiempo mínimo entre fichas (segundos)
```

#### Cómo funciona
```python
ultimo_conteo = 0

# Al detectar flanco descendente
if tiempo_actual - ultimo_conteo >= DEBOUNCE_TIME:
    # Contar la ficha
    fichas_restantes -= 1
    ultimo_conteo = tiempo_actual
else:
    # Ignorar - es un rebote
    print("[REBOTE IGNORADO]")
```

### Ajustar el Tiempo de Anti-Rebote

El valor de `DEBOUNCE_TIME` depende de:
1. **Velocidad del motor**: Más rápido = tiempo menor
2. **Tipo de fichas**: Más grandes = tiempo mayor
3. **Características del sensor**: Sensibilidad

#### Valores recomendados:
- **Motor lento**: 0.5 segundos (2 fichas por segundo)
- **Motor medio**: 0.3 segundos (3 fichas por segundo) ← **ACTUAL**
- **Motor rápido**: 0.2 segundos (5 fichas por segundo)

#### Cómo ajustar:
1. Editar `expendedora_core.py`
2. Cambiar el valor de `DEBOUNCE_TIME`
3. Reiniciar el sistema
4. Probar con una cantidad conocida de fichas

### Prueba de Calibración

```bash
# Agregar 10 fichas
# Verificar cuántas salen realmente
# Si salen más de 10: AUMENTAR DEBOUNCE_TIME
# Si salen menos de 10: DISMINUIR DEBOUNCE_TIME (cuidado)
```

## Problema 3: El motor no arranca cuando se agregan fichas

### Síntomas
- Se agregan fichas desde la GUI
- El contador de fichas restantes aumenta
- El motor NO se enciende

### Posibles causas:
1. El hilo de control no está corriendo
2. El pin del motor no está configurado
3. Hay un error en la lógica de control

### Verificación:
```python
# Verificar que el hilo está activo
print("[DEBUG] Motor activo:", core.motor_activo)
print("[DEBUG] Fichas restantes:", core.obtener_fichas_restantes())
print("[DEBUG] Estado pin motor:", GPIO.input(core.MOTOR_PIN))
```

### Solución:
1. Verificar que `core.iniciar_sistema()` se llama en `main.py`
2. Verificar que no hay excepciones en el hilo
3. Revisar los logs en consola

## Problema 4: La GUI muestra valores incorrectos

### Síntomas
- Los contadores muestran valores extraños
- Decimales donde deberían ser enteros
- Formato incorrecto

### Solución Implementada:
```python
def actualizar_contadores_gui(self):
    for key in self.contadores_labels:
        valor = self.contadores[key]
        if key == "dinero_ingresado":
            texto = f"Dinero Ingresado: ${valor:.2f}"
        else:
            texto = f"{key.title()}: {int(valor)}"
        self.contadores_labels[key].config(text=texto)
```

## Problema 5: El motor no se apaga cuando fichas_restantes llega a 0

### Síntomas
- Todas las fichas salieron
- `fichas_restantes = 0`
- El motor sigue funcionando

### Causa probable:
El contador del hardware y la GUI están desincronizados

### Solución:
1. Verificar que `actualizar_desde_hardware()` se está ejecutando
2. Revisar que el sensor está contando correctamente
3. Verificar el anti-rebote no es demasiado alto

### Debug:
```python
# En el hilo de control, agregar:
print(f"[DEBUG] Check motor: fichas={fichas_restantes}, motor={motor_activo}")
```

## Configuración Recomendada para Hardware Real

```python
# expendedora_core.py

# Para Raspberry Pi con GPIO real:
# import RPi.GPIO as GPIO

# Para pruebas en PC:
# from gpio_sim import GPIO

# Ajustar según tu hardware:
MOTOR_PIN = 24              # Pin del motor
ENTHOPER = 23               # Pin del sensor
DEBOUNCE_TIME = 0.3         # Ajustar según velocidad del motor

# Ajustar según velocidad de actualización deseada:
# En expendedora_gui.py, línea ~570:
self.root.after(500, self.actualizar_desde_hardware)  # 500ms
```

## Checklist de Diagnóstico

Si algo no funciona, verificar en orden:

- [ ] El sistema se inicia correctamente (`core.iniciar_sistema()`)
- [ ] Los pines GPIO están configurados
- [ ] El hilo de control está corriendo
- [ ] Los contadores inician en 0
- [ ] Al agregar fichas, el contador aumenta
- [ ] El motor se enciende cuando `fichas_restantes > 0`
- [ ] El sensor detecta las fichas
- [ ] El contador disminuye cuando salen fichas
- [ ] El motor se apaga cuando `fichas_restantes == 0`
- [ ] La GUI se actualiza cada 500ms

## Logs Útiles

Buscar en la salida de consola:

```
[MOTOR ON] Fichas pendientes: X        ← Motor encendido
[FICHA EXPENDIDA] Restantes: X         ← Ficha contada correctamente
[REBOTE IGNORADO]                      ← Anti-rebote funcionando
[MOTOR OFF] Todas las fichas expendidas ← Motor apagado correctamente
```

## Ajustes Finos

### Si el motor es muy rápido:
- Aumentar `DEBOUNCE_TIME` a 0.4 o 0.5
- Considerar reducir la velocidad del motor (hardware)

### Si el motor es muy lento:
- Disminuir `DEBOUNCE_TIME` a 0.2 o 0.15
- Cuidado con no permitir rebotes

### Si la GUI no responde:
- Aumentar el intervalo de actualización de 500ms a 1000ms
- Verificar que no hay bloqueos en el hilo principal
