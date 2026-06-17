---
name: python-conventions
description: Convenciones Python para este repo — estilo, tests, sin over-engineering. Usar al escribir o revisar código Python en expendedora/ o tests/.
paths: "**/*.py"
---

# Python — Expendedora

Basado en [swell-agents/coding-skills python-conventions](https://github.com/swell-agents/coding-skills/tree/main/skills/python-conventions), adaptado a este proyecto (pip, unittest, sin uv obligatorio).

## Estilo

- PEP 8; líneas legibles; **nombres y comentarios en español** en dominio de negocio (`fichas_restantes`, `tolva`, `pin`, `controlador`)
- Preferir `pathlib.Path` para rutas nuevas
- Imports: stdlib → terceros → `expendedora.*`
- No `print` nuevo en lógica crítica salvo logs operativos existentes (`[ESP32]`, `[STATE]`, `[AUTH]`)

## Cambios

- **Mínimo diff** que resuelve el problema
- Sin abstracciones de una sola línea ni helpers que solo envuelven un call
- Reutilizar `ConfigRepository`, `StateRepository`, `AppController` antes de crear módulos nuevos
- **Sin fachadas** que solo reexporten funciones

## Tests

- Framework: `unittest` en `tests/`
- Mockear solo I/O (MySQL, serial, HTTP); preferir objetos reales para `MachineState` / `CounterService`
- Tras cambios en persistencia o bridge: correr `python -m unittest discover -s tests -p "test_*.py"`

## Seguridad

- No commitear `config.local.json` ni passwords
- Parametrizar SQL; no formatear queries con f-strings de input usuario

## Verificación

Invocar skill `expendedora-verify` antes de cerrar tareas de código.
