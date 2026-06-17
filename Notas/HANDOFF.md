# HANDOFF - v2.0.0

Fecha: 2026-06-17
Estado declarado: v2.0.0 — arquitectura en capas, Arduino estable, destrabe desde ayuda

## Objetivo general alcanzado

Se estabilizo el flujo completo de expendedora con Arduino/Mega:

- Conexion serial robusta desde Python.
- Aplicacion abre correctamente despues de login.
- Motor/sensor funcionando en ciclo real.
- Conteo y reportes alineados con eventos del MCU.
- Separacion correcta entre contadores globales y de sesion/parcial.

## Cambios principales implementados

### 1) Comunicacion serial y handshake

- Mejora de autodeteccion y handshake en backend serial.
- Reintentos y backoff de reconexion en el bridge.
- Diagnosticos mas claros en logs para `HELLO/READY/DICT/CONFIG`.
- Ajuste de baudios a `115200` en ambos lados:
  - Firmware (`Serial.begin(115200)`).
  - App (`config.json` y defaults de cliente serial).

### 2) Estabilidad de arranque de app (login -> GUI)

- Correccion de ciclo de vida Tkinter para evitar cierre silencioso.
- Se evita destruir root prematuramente tras login.
- `main.py` con trazas de arranque para diagnostico rapido.

### 3) Motor y reglas de activacion

- Regla de negocio reforzada: si `fichas_restantes > 0`, se sincroniza `SET_TARGET`.
- Mejor sincronizacion al reconectar backend.
- Limpieza de estados de emergencia al completar destrabe (`UNJAM_DONE`).
- Ajustes de pines operativos (motor/reversa/sensor en 10/12/9).

### 4) CONFIG al MCU (JSON parse)

- Se redujo carga de `CONFIG` enviada desde PC:
  - Frames mas compactos.
  - Separacion de partes para minimizar errores de parseo.
- Mejora de retry de `CONFIG` hasta aplicacion correcta.

### 5) Sensor, sobre-dispensa y corte de motor

- Ajuste de deteccion de flancos en firmware segun señal real del sensor.
- Ajustes de filtros/tiempos para evitar perdida de tokens validos.
- Se prioriza decision del MCU para corte (remaining autoritativo).
- Bridge adaptado para no descartar tokens validos por debounce PC cuando MCU ya conto.

### 6) Conteo de fichas expendidas y reportes

- Restaurado incremento de `fichas_expendidas` en ruta MCU:
  - Si baja `remaining`, se registra delta de fichas expendidas.
- Trigger de telemetria al finalizar tanda (`fichas_restantes == 0`) con deduplicacion.
- Evita doble envio por secuencia `TOKEN + RUN_DONE`.

### 7) Contadores global vs sesion/parcial

- En cierre de sesion:
  - Se preserva `contadores_global`.
  - Se reinicia solo `contadores_parcial` y sesion.
  - Se evita resetear acumulados globales de fichas expendidas.
- Se ajustaron bases de sincronizacion para continuidad global y reinicio parcial limpio.

## Mejoras de observabilidad

- Logs de decisiones en bridge (`SET_TARGET`, omisiones, reconexion, sync).
- Logs de motor/sensor en firmware y lado PC para auditoria de eventos.
- Mejor trazabilidad de estados: `TOKEN`, `RUN_DONE`, `MOTOR_ON/OFF`, `JAM`, `UNJAM_DONE`.

## Principales trabas encontradas y resolucion

1. **COM ocupado / acceso denegado**
   - Sintoma: no conecta COM4, motor no arranca por falta de backend online.
   - Causa: otra app o monitor serie usando el mismo puerto.
   - Resolucion: liberar puerto y dejar unica instancia.

2. **`ERR json_parse` en `CONFIG`**
   - Sintoma: no aplicaba config, `SET_TARGET` quedaba pendiente.
   - Causa: payload/config y condiciones serial que provocaban parse fallido.
   - Resolucion: compactacion de frames + retry + ajustes de enlace.

3. **Sobre-dispensa / duplicidad de fichas**
   - Sintoma: salian mas fichas que target.
   - Causa: desfasajes en flancos y filtros demasiado agresivos en token gap.
   - Resolucion: ajuste de flancos, calibracion y uso de `remaining` MCU como autoridad.

4. **Contador de fichas expendidas en 0**
   - Sintoma: reportes no se enviaban al terminar tanda.
   - Causa: ruta MCU actualizaba `remaining` pero no incrementaba expendidas.
   - Resolucion: registrar delta de expendidas en TOKEN ruta MCU.

5. **Global reiniciado en logout**
   - Sintoma: cierre diario quedaba contaminado por resets de sesion.
   - Causa: `cerrar_sesion()` reseteaba global y parcial.
   - Resolucion: preservar global, resetear solo parcial/sesion.

## Errores observados (historial)

- `PermissionError(13, 'Acceso denegado.')` en COM.
- `ERR json_parse` en firmware durante `CONFIG`.
- `ImportError` por funcion faltante (`cmd_dict`) tras rollback.
- API local respondiendo `500` en heartbeat/telemetria (cloud OK en pruebas).

## Estado operativo recomendado

- Mantener `baud=115200` en firmware y app.
- Evitar abrir monitor serie mientras corre `main.py`.
- Usar el flujo normal:
  - Carga fichas -> expende -> `remaining` llega a 0 -> envio telemetria.
- Cierre de sesion:
  - Reinicia parcial/sesion.
  - Conserva acumulado global para cierre diario.

## Arquitectura (2026-06-09)

Reestructuración en 3 capas (`expendedora/`):

- **Interfaz** → solo `AppController`
- **Lógica** → `MachineState`, `SerialBridge`, servicios de dispensado/sesión
- **Persistencia** → `StateRepository`, `ConfigRepository`, MySQL, HTTP remoto

Incongruencias cerradas en esta migración:

- Escrituras activas a `registro.json` eliminadas (solo lectura legacy en recover)
- `vaciar_buffer` centralizado con `revert_all_pending_lots`
- API contadores renombrada (`get_fichas_sesion`, `get_fichas_acumuladas`)
- Label GUI: Arduino (no ESP32)
- Pines unificados: 10/12/9 en config, firmware y docs
- Tests: 47 unittest (capas, bridge TOKEN/JAM/telemetría, sesión AppController, config, state_store)
- GUI mixins partidos: `layout_*` y `admin_*` (ningún archivo > ~430 líneas)

## Pendientes sugeridos (opcional)

- Checklist en campo con Arduino (`/.cursor/skills/expendedora-field-validation`): 1/2/5/10 fichas, telemetría, JAM.
- Revisar endpoint local que devuelve `500` en heartbeat/telemetría.

---

Si se retoma trabajo desde este punto, tomar este archivo como baseline funcional y verificar primero:

1) Conexion serial estable en COM,
2) Conteo 1:1 token/ficha,
3) Telemetria al llegar `fichas_restantes` a 0.

