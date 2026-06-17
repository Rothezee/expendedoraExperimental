---
name: expendedora-verify
description: Verifica cambios en expendedora antes de dar por terminado — imports, tests unittest, smoke bootstrap. Usar tras refactors, limpieza legacy o cambios en capas/persistencia.
paths: expendedora/**,tests/**,main.py
---

# Verificar antes de terminar

Inspirado en [swell-agents/coding-skills](https://github.com/swell-agents/coding-skills) `reviewing-changes` y prácticas verify-before-done.

## 1. Imports críticos

```powershell
python -c "from expendedora.interface.main import run_kiosk_loop; from expendedora.logic.application.bootstrap import create_app_controller; from expendedora.interface.gui.app import ExpendedoraGUI; app=create_app_controller(); app.start(); app.stop(); print('OK')"
```

## 2. Tests

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Si falla `Start directory is not importable`, confirmar que existe `tests/__init__.py`.

## 3. Rutas de persistencia

- JSON solo bajo `expendedora/persistence/json/`
- No debe existir carpeta `persistencia/` en raíz
- `grep` sin hits: `infra/`, `shared_buffer`, `expendedora_gui`, `User_management`

## 4. Capas (manual rápido)

- `interface/gui/` no importa `persistence` (salvo `auth/` → `cashier_database`)
- `logic/` no importa `interface`
- `persistence/` no importa `logic.services`

## 5. Smoke opcional GUI

Solo si hay display:

```powershell
python main.py
```

Login sin sesión → exit 0 es válido. Buscar crash o traceback.

## Criterio de done

- Tests verdes (o explicar cuáles faltan y por qué)
- Smoke imports OK
- Sin referencias legacy reintroducidas
- Usuario informado si requiere prueba en hardware (`/expendedora-field-validation`)
