"""Variables de entorno del modo kiosco."""

import os


def kiosk_mode_habilitado() -> bool:
    return str(os.environ.get("EXPENDEDORA_KIOSK", "")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
