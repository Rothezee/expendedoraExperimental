---
name: expendedora-review
description: Revisión enfocada en expendedora — capas, serial/contadores, persistencia, seguridad MySQL/PIN. Usar antes de merge, release o tras cambios en bridge/state_store/auth.
paths: expendedora/**
---

# Code review — Expendedora

Adaptación del flujo [reviewing-changes](https://github.com/swell-agents/coding-skills/tree/main/skills/reviewing-changes) a este dominio.

## Pass 1 — Código y dominio

- Conteo 1:1: ¿TOKEN/SYNC alteran `fichas_restantes` y pending lots correctamente?
- ¿Logout preserva contadores globales y resetea sesión?
- ¿`vaciar_buffer` revierte pending lots antes de zerar buffer?
- ¿Duplicación o fachadas nuevas?
- ¿Mixins >500 líneas sin justificación?

## Pass 2 — Seguridad

- Credenciales solo en `config.local.json` o env, nunca hardcodeadas
- PINs: no loguear en claro
- SQL parametrizado en `auth_repository` / `report_repository`
- HTTP: timeouts en telemetría; no bloquear UI

## Pass 3 — Arquitectura

- Capas según `.cursor/rules/expendedora-layers.mdc`
- JSON writers solo en `persistence/json`
- GUI → `AppController` únicamente (excepto auth MySQL directo acordado)

## Pass 4 — Aceptación

- ¿El diff resuelve lo pedido sin scope creep?
- ¿Docs (`OPERACION.md`, firmware README) alineados si cambian pines/rutas?

## Pass 5 — Hardware / regresión

- ¿Requiere checklist de campo? → invocar `expendedora-field-validation`
- ¿Cambió protocolo? → verificar `protocol.py` y `esp32_dispenser.ino` sincronizados

## Formato de salida

```markdown
## Review Expendedora

| Área | Veredicto | Notas |
|------|-----------|-------|
| Dominio/contadores | pass/warn/fail | |
| Seguridad | pass/warn/fail | |
| Capas | pass/warn/fail | |
| Docs/hardware | pass/warn/fail | |

### Acciones (ordenadas por severidad)
1. ...
```

Solo lectura — no editar el diff; reportar hallazgos.
