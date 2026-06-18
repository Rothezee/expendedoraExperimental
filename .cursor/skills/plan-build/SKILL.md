---
name: plan-build
description: >-
  Ejecuta el plan activo paso a paso desde .cursor/plans/active-plan.md.
  Usar tras plan-spec, cuando review devuelva NEEDS_BUILD, o al pedir
  "build", "implementar el plan", "seguir la fase".
disable-model-invocation: true
---

# Plan Build — construir según el plan

**Implementación.** Seguir el plan; no renegociar scope salvo bloqueo documentado.

## Prerrequisito

Debe existir `.cursor/plans/active-plan.md`. Si no:

1. Invocar `plan-spec` con el pedido del usuario.
2. No improvisar sin plan.

## Inicio de cada sesión build

1. Leer `active-plan.md` completo.
2. Localizar el **primer paso** `- [ ]` pendiente (orden F1→Fn, paso→paso).
3. Anunciar en una línea: `BUILD → Fx.y: [texto del paso]`.

Si el plan está en `en_review` con fixes pendientes, ejecutar la **lista numerada del último review** antes de pasos nuevos.

## Reglas de ejecución

### Alcance

- **Un paso por iteración** (salvo que el usuario pida "toda la fase Fx").
- Diffs mínimos; no refactorizar fuera del paso.
- Respetar reglas del repo y skills de dominio.

### Durante el paso

1. Leer contexto del plan + archivos tocados.
2. Implementar.
3. Correr **verificación del paso o fase** (del plan).
4. Si falla → arreglar dentro del mismo paso; no marcar `[x]` hasta verde.

### Al completar paso

1. Marcar `- [x]` en `active-plan.md`.
2. Actualizar `Estado` → `en_build`, `Última actualización`, fila en **Bitácora**.
3. Si todos los pasos de la fase están `[x]` → correr verificación de fase completa.

## Handoff obligatorio (fin de turno)

Elegir **uno**:

```text
HANDOFF → plan-review
Motivo: fase Fx completada | paso Fx.y completado | fixes del review aplicados
```

```text
HANDOFF → plan-spec
Motivo: bloqueo arquitectónico — [descripción]
```

```text
HANDOFF → done
Motivo: todos los criterios globales cumplidos y review previo APPROVED
```

Incluir siempre:

- Pasos completados en esta sesión.
- Comandos ejecutados y resultado (OK / fallo).
- Archivos modificados (lista corta).

## Bloqueos

Si un paso no se puede completar:

- Documentar en **Bitácora** del plan.
- No marcar `[x]`.
- Proponer ajuste mínimo al plan vía `plan-spec` (no cambiar el plan a mano sin reflejar el porqué).

## Integración expendedora

Si el plan toca `expendedora/` o `tests/`:

- Tras cada fase (o al HANDOFF final): invocar `expendedora-verify`.
- Hardware/protocolo: anotar en plan si falta prueba en máquina.

## Anti-patrones

- Saltar pasos "porque ya sé cómo".
- Marcar criterios de aceptación sin ejecutar verificación.
- Expandir scope "de paso" sin actualizar el plan en spec.
