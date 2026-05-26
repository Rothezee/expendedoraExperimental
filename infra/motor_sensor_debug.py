"""
Logs de depuración motor/sensor (PC). Activar en config.json → hardware.esp32.debug_motor_sensor
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def debug_enabled(config: Optional[Dict[str, Any]] = None) -> bool:
    if not isinstance(config, dict):
        return False
    hardware = config.get("hardware", {})
    if not isinstance(hardware, dict):
        return False
    esp = hardware.get("esp32", {})
    if not isinstance(esp, dict):
        return False
    return bool(esp.get("debug_motor_sensor", False))


def dbg_log(config: Optional[Dict[str, Any]], category: str, message: str) -> None:
    if not debug_enabled(config):
        return
    print(f"[DBG {category}] {message}")
