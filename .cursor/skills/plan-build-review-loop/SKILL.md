---
name: plan-build-review-loop
description: >-
  Orquesta el ciclo plan-spec → plan-build → plan-review hasta APPROVED o tope
  de iteraciones. Usar con "loop de plan", "spec build review", automatizar
  calidad del plan, o cuando el usuario quiera un flujo completo sin microgestionar.
disable-model-invocation: true
---

# Loop Spec → Build → Review

Ciclo cerrado de calidad. **Un rol por turno**: no mezclar spec, build y review en la misma respuesta salvo emergencia.

## Artefacto compartido

Todo el ciclo lee/escribe **`.cursor/plans/active-plan.md`**.

Campos de control en el plan:

- `Estado`: draft → en_build → en_review → aprobado
- `Iteración review`: N / 5

## Diagrama

```text
Usuario / pedido
       ↓
  [plan-spec] ──NEEDS_REPLAN──┐
       ↓                       │
  [plan-build] ←──NEEDS_BUILD──┤
       ↓                       │
  [plan-review] ───────────────┘
       ↓
   APPROVED → done (+ expendedora-verify si aplica)
```

## Cuándo arrancar en cada nodo

| Situación | Empezar en |
|-----------|------------|
| Pedido nuevo, sin plan | `plan-spec` |
| Existe plan, pasos pendientes `[ ]` | `plan-build` |
| Build hizo HANDOFF → review | `plan-review` |
| Review = NEEDS_BUILD | `plan-build` (fixes primero) |
| Review = NEEDS_REPLAN | `plan-spec` (ajustar plan, no codear) |
| Review = APPROVED | Cerrar: verify, informar usuario |

## Reglas del loop

1. **Máximo 5 iteraciones review** por plan (configurable en el plan). Tras el tope → `APPROVED_WITH_GAPS` o pedir decisión al usuario.
2. **Build antes de review**: no revisar un paso no implementado salvo review exploratorio explícito.
3. **Review antes de "done"**: no declarar terminado sin veredicto APPROVED.
4. **Una fase por ciclo build→review** (recomendado): reduce drift y facilita debug.
5. Tras APPROVED en proyectos expendedora: ejecutar `expendedora-verify`; si falla → NEEDS_BUILD implícito.

## Prompt de una línea (copiar al chat)

```text
/plan-build-review-loop [pedido o "continuar"]
```

Comportamiento:

- Sin plan → spec con el pedido.
- Con plan → leer Estado/Handoff y continuar en el nodo correcto.

## Automatización con /loop (opcional)

Para iterar sin intervención manual en la misma sesión:

```text
/loop plan-build-review-loop continuar
```

Modo **dinámico** (ver skill `loop`): tras cada review NEEDS_BUILD, el agente vuelve a build en el siguiente turno; tras APPROVED, **no** rearmar el loop.

## Mensajes de handoff estándar

Build termina con:

```text
HANDOFF → plan-review
```

Review termina con:

```text
SIGUIENTE: plan-build — aplicar fixes 1..N
```

o

```text
SIGUIENTE: plan-spec — [motivo replan]
```

o

```text
SIGUIENTE: done — plan aprobado
```

## Cierre al usuario

Cuando el loop termina, resumir:

- Objetivo del plan vs resultado.
- Fases completadas.
- Iteraciones build/review usadas.
- Comandos de verificación finales.
- Pendientes opcionales (warns) post-merge.

## Ejemplo mínimo

1. Usuario: "Agregar TEST_DISPENSE al firmware y ayuda"
2. **spec** → plan F1 protocolo, F2 firmware, F3 GUI, F4 tests
3. **build** F1 → HANDOFF review
4. **review** NEEDS_BUILD (falta test) → build fix → review APPROVED F1
5. **build** F2… repetir
6. **verify** global → done
