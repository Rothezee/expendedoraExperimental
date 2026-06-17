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
| `expendedora-field-validation` | Checklist hardware antes de release |
| `expendedora-verify` | Tests + smoke tras cambios de código |
| `expendedora-review` | Review enfocada dominio/capas/seguridad |
| `python-conventions` | Estilo Python (adaptado de swell-agents) |

Invocar en chat: mencionar el nombre o pedir explícitamente la skill.

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
