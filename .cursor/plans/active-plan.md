# Plan: Auditoría menú Ayuda + Manual

**Estado**: aprobado  
**Iteración review**: 1 / 5  
**Creado**: 2026-06-18  
**Última actualización**: 2026-06-18  

## Objetivo

Verificar menú **Ayuda** + **Manual** y corregir gaps según decisiones del usuario.

## Fase F2 — Fixes (completada)

- [x] F2.1 Destrabar (header) = mismo flujo que `help_motor_trabado`
- [x] F2.2 Summary motor trabado corregido en help_content
- [x] F2.3 `help_arduino_sin_conexion`: sin doble confirmación
- [x] F2.4 `_run_help_scenario`: error si handler inexistente
- [x] F2.5 Manual: sección menú Ayuda (5 casos)
- [x] F2.6 Tests actualizados; eliminado help_combo_values
- [x] F2.7 Reinicio kiosk en `help_reiniciar_app` (EXPENDEDORA_KIOSK=1)

## Verificación

- [x] 89 tests OK

## Bitácora

| Fecha | Agente | Acción |
|-------|--------|--------|
| 2026-06-18 | spec/review | Auditoría inicial |
| 2026-06-18 | build | Fixes según respuestas usuario |
| 2026-06-18 | review | APPROVED |
