---
name: plan-review
description: >-
  Compara la implementación contra .cursor/plans/active-plan.md y el diff.
  Devuelve APPROVED, NEEDS_BUILD o NEEDS_REPLAN con lista priorizada de fixes.
  Usar tras plan-build, antes de merge/release, o al pedir "review del plan".
disable-model-invocation: true
---

# Plan Review — ¿lo construido cumple el plan?

**Auditoría.** Preferir readonly; solo lectura de código y `git diff`. No implementar fixes (eso es `plan-build`).

## Prerrequisito

- `.cursor/plans/active-plan.md` existe.
- Hubo al menos un `plan-build` (o cambios locales relevantes).

Actualizar en el plan: `Estado` → `en_review`.

## Proceso

### 1. Recolectar evidencia

- Leer plan completo (fases, criterios, fuera de alcance).
- `git diff` / `git status` (o archivos indicados en bitácora build).
- Ejecutar **verificaciones del plan** si build no las corrió (tests, smoke).

### 2. Evaluar cada criterio de aceptación

Por cada `CA-Fx.y` del plan:

| Estado | Significado |
|--------|-------------|
| **pass** | Cumplido con evidencia |
| **warn** | Cumplido parcialmente o sin verificar en runtime |
| **fail** | No cumplido o regresión |

Evidencia = comando + salida, cita de código, o test que pasa/falla.

### 3. Evaluar calidad transversal

Checklist rápido (adaptar al repo):

- [ ] Scope: ¿diff solo toca lo del plan?
- [ ] Reglas/capas del proyecto respetadas.
- [ ] Tests añadidos o actualizados si el plan lo pedía.
- [ ] Docs alineados si cambió operación/API.
- [ ] Sin deuda obvia introducida en el mismo diff.

Para expendedora: considerar también `expendedora-review` en dominio/seguridad si el diff es grande.

### 4. Veredicto global

| Veredicto | Condición | Siguiente skill |
|-----------|-----------|-----------------|
| **APPROVED** | Todos los CA **pass** (warns documentados y aceptables); verificación global OK | `done` / commit / release |
| **NEEDS_BUILD** | Algún **fail** o **warn** corregible sin replan | `plan-build` |
| **NEEDS_REPLAN** | Plan incorrecto, alcance imposible, o decisión arquitectónica nueva | `plan-spec` |

Incrementar `Iteración review` en el plan (máx. **5** por defecto).

Si iteración ≥ máximo y quedan fails → reportar **APPROVED_WITH_GAPS** con gaps explícitos; no seguir el loop automático.

### 5. Criterio "no puede quedar mejor"

Cerrar loop (APPROVED) cuando:

- Todos los CA del plan en **pass**.
- Verificación global ejecutada y OK.
- Segunda pasada de review sin nuevos **fail** (solo warns opcionales).
- Mejoras restantes son cosméticas → listar como "opcional post-merge", no bloquear.

## Formato de salida (obligatorio)

```markdown
## Plan Review — [título del plan]

**Iteración**: N / 5  
**Veredicto**: APPROVED | NEEDS_BUILD | NEEDS_REPLAN | APPROVED_WITH_GAPS

### Criterios de aceptación

| ID | Estado | Evidencia |
|----|--------|-----------|
| CA-F1.1 | pass/fail/warn | … |

### Scope y calidad

| Área | Estado | Notas |
|------|--------|-------|
| Alcance vs plan | pass/warn/fail | |
| Tests/verify | pass/warn/fail | |
| Reglas proyecto | pass/warn/fail | |

### Acciones para build (solo si NEEDS_BUILD)

Prioridad alta → baja:

1. [Fx.y / CA-…] Descripción concreta del fix
2. …

### Siguiente paso

`plan-build` | `plan-spec` | `done`

**Instrucción para el agente/usuario**: [una frase copiable]
```

Escribir la **lista numerada de acciones** también en la sección **Bitácora** o un bloque `## Fixes pendientes (review)` al final de `active-plan.md` para que `plan-build` la consuma.

## Anti-patrones

- Aprobar sin correr verificación cuando el plan la define.
- Implementar fixes en la misma sesión review (rompe el loop).
- Replanear por preferencias de estilo menores → usar NEEDS_BUILD.
