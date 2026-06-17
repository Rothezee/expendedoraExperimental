"""Rutas canónicas de archivos JSON (directorio `expendedora/persistence/json/`)."""

from __future__ import annotations

import shutil
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
JSON_DATA_DIR = Path(__file__).resolve().parent / "json"
_LEGACY_DIRS = (
    _PROJECT_ROOT / "persistencia",
    _PROJECT_ROOT,
)

CONFIG_FILE = str(JSON_DATA_DIR / "config.json")
CONFIG_LOCAL_FILE = str(JSON_DATA_DIR / "config.local.json")
STATE_FILE = str(JSON_DATA_DIR / "machine_state.json")
LEGACY_BUFFER_FILE = str(JSON_DATA_DIR / "buffer_state.json")
REGISTRO_FILE = str(JSON_DATA_DIR / "registro.json")
PENDING_SYNC_FILE = str(JSON_DATA_DIR / "pending_cashier_sync.json")

_DATA_FILENAMES = (
    "config.json",
    "config.local.json",
    "machine_state.json",
    "machine_state.json.bak",
    "buffer_state.json",
    "registro.json",
    "pending_cashier_sync.json",
)

_UPDATER_PRESERVE_FILES = tuple(
    str((JSON_DATA_DIR.relative_to(_PROJECT_ROOT) / name).as_posix())
    for name in _DATA_FILENAMES
    if name != "config.local.json"
)


def ensure_persistence_dir() -> Path:
    JSON_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return JSON_DATA_DIR


def migrate_legacy_data_files() -> None:
    """Copia JSON desde ubicaciones legacy si aún no existen en `persistence/json/`."""
    ensure_persistence_dir()
    for name in _DATA_FILENAMES:
        target = JSON_DATA_DIR / name
        if target.exists():
            continue
        for legacy_dir in _LEGACY_DIRS:
            legacy = legacy_dir / name
            if legacy.is_file():
                shutil.copy2(legacy, target)
                break
