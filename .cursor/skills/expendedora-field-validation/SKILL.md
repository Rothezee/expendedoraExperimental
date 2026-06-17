---
name: expendedora-field-validation
description: Ejecuta el checklist de validación en hardware real para la expendedora (serial, conteo 1:1, telemetría, cierres). Usar antes de release, tras cambios en serial_bridge, firmware, machine_state o persistencia.
paths: expendedora/logic/hardware/**,firmware/**,expendedora/persistence/**
---

# Validación en campo — Expendedora

Baseline: `Notas/HANDOFF.md` y `Notas/OPERACION.md`.

## Pre-requisitos

1. Arduino conectado por USB; monitor serial **cerrado**
2. `expendedora/persistence/json/config.json` con pines 10/12/9 y `baud: 115200`
3. `codigo_hardware` / `device_id` configurado si se prueba telemetría
4. MySQL: `config.local.json` con credenciales si se prueba login/cajeros

## Checklist obligatorio

| # | Prueba | Esperado |
|---|--------|----------|
| 1 | Arranque `python main.py` | Login abre; consola `[ARDUINO] READY` o reintento sin crash |
| 2 | Dispensar **1** ficha | 1 TOKEN, `fichas_restantes` → 0, contador +1 |
| 3 | Dispensar **2** fichas | 2 TOKENs, sin sobre-dispensa |
| 4 | Dispensar **5** y **10** fichas | Conteo 1:1 con sensor |
| 5 | Telemetría | Al llegar `remaining=0`, log `[API]` sin error 500 persistente |
| 6 | Logout | Sesión resetea; **global** de fichas se conserva |
| 7 | Corte simulado | Matar app mid-dispense; reiniciar → `[STATE] Recuperado desde: ...` coherente |
| 8 | JAM / UNJAM | Timeout → JAM; destrabe → `UNJAM_DONE`, emergencia limpia |

## Logs a buscar

```
[ARDUINO] TOKEN tolva N | restantes=X
[ARDUINO] READY ...
[STATE] Recuperado desde: machine_state+config
[NET] telemetria -> 200
[NET] heartbeat -> 200
```

## Si falla

| Síntoma | Revisar |
|---------|---------|
| Sin READY | COM ocupado, cable, `auto_detect`, permisos puerto |
| Doble conteo | `pulso_min_s`, rebote sensor, dedupe TOKEN/RUN_DONE en bridge |
| 403 telemetría | `codigo_hardware` vacío en config |
| MySQL login | `mysql.production` / `mysql.local`, `config.local.json` |

## Al terminar

Reportar tabla pass/fail por ítem y pegar logs relevantes (últimas 30 líneas de serial/API).
