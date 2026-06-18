# Cursor — reglas y skills del proyecto

## Reglas (auto-cargadas)

| Archivo | Alcance |
|---------|---------|
| `rules/expendedora-core.mdc` | Siempre |
| `rules/expendedora-layers.mdc` | `expendedora/**/*.py` |
| `rules/expendedora-persistence.mdc` | `expendedora/persistence/**` |
| `rules/expendedora-firmware.mdc` | `firmware/**`, `logic/hardware/**` |
| `rules/expendedora-gui.mdc` | `expendedora/interface/**` |

## Skills del proyecto (`.cursor/skills/`)

| Skill | Uso |
|-------|-----|
| `plan-spec` | Diseñar plan ejecutable con criterios de aceptación |
| `plan-build` | Implementar paso a paso el plan activo |
| `plan-review` | Auditar cumplimiento vs plan; devolver fixes a build |
| `plan-build-review-loop` | Orquestar spec → build → review hasta APPROVED |
| `expendedora-field-validation` | Checklist hardware antes de release |
| `expendedora-verify` | Tests + smoke tras cambios de código |
| `expendedora-review` | Review enfocada dominio/capas/seguridad |
| `python-conventions` | Estilo Python (adaptado de swell-agents) |

Invocar en chat: mencionar el nombre o pedir explícitamente la skill.

### Loop spec / build / review

1. Pedir plan: `plan-spec` + descripción del trabajo → escribe `.cursor/plans/active-plan.md`
2. Construir: `plan-build` (un paso o fase por turno)
3. Revisar: `plan-review` → si `NEEDS_BUILD`, volver a `plan-build`
4. Automatizar: `plan-build-review-loop` o `/loop plan-build-review-loop continuar`

Ver [plan-build-review-loop/SKILL.md](skills/plan-build-review-loop/SKILL.md).

## Skills externas recomendadas (GitHub)

Instalar vía **Cursor Settings → Rules → Add from GitHub** o copiar carpetas a `.cursor/skills/`:

| Repo | Skill útil | Para qué |
|------|------------|----------|
| [swell-agents/coding-skills](https://github.com/swell-agents/coding-skills) | `reviewing-changes` | Review 5 pasos (código, seguridad, arquitectura) |
| [swell-agents/coding-skills](https://github.com/swell-agents/coding-skills) | `engineering-philosophy` | KISS, YAGNI, DRY en refactors |
| [swell-agents/coding-skills](https://github.com/swell-agents/coding-skills) | `committing-changes` | Mensajes de commit y PRs pequeños |

Este repo ya incluye versiones adaptadas: `python-conventions`, `expendedora-review`.

## Built-in Cursor

- `/review-bugbot` — bugs en el diff local
- `/review-security` — superficie MySQL, credenciales, HTTP
