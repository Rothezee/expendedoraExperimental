---
name: plan-spec
description: >-
  Convierte un pedido vago en un plan ejecutable con criterios de aceptación,
  fases y verificación. Usar al iniciar tareas grandes, refactors, features
  nuevas, o cuando el usuario pida "plan", "spec", "diseñar antes de codear".
disable-model-invocation: true
---

# Plan Spec — diseñar antes de construir

**Solo planificación.** No editar código productivo ni commitear. Exploración readonly permitida.

## Entrada

- Pedido del usuario (puede ser ambiguo).
- Reglas del repo (`.cursor/rules/`, `.cursorrules`) y skills de dominio si aplican.

## Salida obligatoria

Escribir o actualizar **`.cursor/plans/active-plan.md`** con el template de [plan-template.md](plan-template.md).

Al cerrar, anunciar:

```text
PLAN LISTO → siguiente: plan-build (fase 1) o plan-build-review-loop
```

## Proceso (orden fijo)

### 1. Aclarar objetivo

- **Problema**: qué duele hoy.
- **Resultado**: qué debe ser verdad cuando termine (observable, no "implementar X").
- **Fuera de alcance**: qué NO se toca (explícito).

Si falta info crítica y no se puede inferir del repo → una sola ronda de preguntas concretas (máx. 3). Si hay default razonable, documentarlo en "Supuestos".

### 2. Inventario mínimo

Leer solo lo necesario (grep, búsqueda semántica, 2–5 archivos clave). Anotar:

- Archivos/módulos a tocar.
- Contratos existentes (APIs, JSON, protocolo serial, tests).
- Riesgos (hardware, MySQL, contadores, Tk).

### 3. Descomponer en fases

Cada fase debe ser **terminable en una sesión de build** (~1 hora de trabajo agente).

Por fase incluir:

| Campo | Contenido |
|-------|-----------|
| ID | `F1`, `F2`, … |
| Objetivo | Una frase |
| Pasos | Checkboxes `- [ ]` numerados |
| Criterios de aceptación | Verificables (comando, test, comportamiento UI) |
| Verificación | Comando concreto o skill (`expendedora-verify`, etc.) |

Reglas de buen plan:

- Pasos **atómicos**: un cambio coherente por checkbox.
- Criterios ** falsables**: evitar "código limpio" sin métrica.
- Dependencias entre fases explícitas.
- Orden: primero lo que desbloquea tests; hardware/docs al final si aplica.

### 4. Estrategia de calidad

Definir en el plan:

- Qué corre en cada fase (tests, lint, smoke).
- Cuándo invocar `plan-review` (fin de cada fase o fin del plan).
- Tope de iteraciones build↔review (default **5**).

### 5. Autorevisión del plan

Antes de entregar, comprobar:

- [ ] ¿Cada criterio tiene cómo comprobarlo?
- [ ] ¿Hay scope creep escondido?
- [ ] ¿El plan respeta capas/reglas del proyecto?
- [ ] ¿Un agente distinto podría ejecutar F1 sin releer todo el chat?

## Anti-patrones

- Planes de 50 pasos sin fases → dividir.
- Pasos "refactorizar todo" → acotar archivos.
- Criterios subjetivos sin verificación.
- Escribir código "de ejemplo" en el plan (solo pseudocódigo o rutas de archivo).

## Relación con otras skills

| Skill | Cuándo |
|-------|--------|
| `plan-build` | Ejecutar pasos del plan |
| `plan-review` | Auditar cumplimiento |
| `plan-build-review-loop` | Orquestar spec→build→review en ciclo |
| `expendedora-verify` | Añadir al plan si toca `expendedora/` o `tests/` |
