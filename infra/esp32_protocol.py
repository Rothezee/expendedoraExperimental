"""
Protocolo line-delimited JSON entre PC y ESP32 (115200 baud).
Cada frame es una línea UTF-8 terminada en \\n.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


PROTOCOL_VERSION = 1


def dumps_frame(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"


def parse_line(line: str) -> Optional[Dict[str, Any]]:
    text = (line or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def cmd_hello() -> Dict[str, Any]:
    return {"dir": "cmd", "type": "HELLO", "v": PROTOCOL_VERSION}


def cmd_dict() -> Dict[str, Any]:
    return {"dir": "cmd", "type": "DICT", "v": PROTOCOL_VERSION}


def cmd_ping() -> Dict[str, Any]:
    return {"dir": "cmd", "type": "PING"}


def cmd_stop() -> Dict[str, Any]:
    return {"dir": "cmd", "type": "STOP"}


def cmd_simulate() -> Dict[str, Any]:
    return {"dir": "cmd", "type": "SIMULATE"}


def cmd_config(
    hopper: Dict[str, Any],
    destrabe: Optional[Dict[str, Any]] = None,
    *,
    debug: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "dir": "cmd",
        "type": "CONFIG",
        "hopper": hopper,
    }
    if destrabe is not None:
        payload["destrabe"] = destrabe
    if debug:
        payload["debug"] = True
    return payload


def cmd_config_destrabe(
    destrabe: Dict[str, Any],
    *,
    debug: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "dir": "cmd",
        "type": "CONFIG",
        "destrabe": destrabe,
    }
    if debug:
        payload["debug"] = True
    return payload


def cmd_config_hoppers(
    hoppers: list,
    destrabe: Optional[Dict[str, Any]] = None,
    *,
    debug: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "dir": "cmd",
        "type": "CONFIG",
        "hoppers": hoppers,
    }
    if destrabe is not None:
        payload["destrabe"] = destrabe
    if debug:
        payload["debug"] = True
    return payload


def cmd_set_target(remaining: int) -> Dict[str, Any]:
    return {"dir": "cmd", "type": "SET_TARGET", "remaining": max(0, int(remaining))}


def cmd_select_hopper(hopper_id: int) -> Dict[str, Any]:
    return {"dir": "cmd", "type": "SELECT_HOPPER", "id": int(hopper_id)}


def cmd_unjam(hopper_id: int, retroceso_s: float) -> Dict[str, Any]:
    return {
        "dir": "cmd",
        "type": "UNJAM",
        "hopper_id": int(hopper_id),
        "retroceso_s": float(retroceso_s),
    }


def hopper_from_tolva(tolva: Dict[str, Any]) -> Dict[str, Any]:
    cal = tolva.get("calibracion", {}) if isinstance(tolva.get("calibracion"), dict) else {}
    rev = tolva.get("motor_pin_rev")
    return {
        "id": int(tolva.get("id", 1)),
        "motor_pin": int(tolva.get("motor_pin", 12)),
        "motor_pin_rev": int(rev) if rev is not None and str(rev).strip() != "" else None,
        "motor_active_low": bool(tolva.get("motor_active_low", True)),
        "sensor_pin": int(tolva.get("sensor_pin", 8)),
        "sensor_bouncetime_ms": int(tolva.get("sensor_bouncetime_ms", 8)),
        "calibracion": {
            "pulso_min_s": float(cal.get("pulso_min_s", 0.05)),
            "pulso_max_s": float(cal.get("pulso_max_s", 0.5)),
            "timeout_motor_s": float(cal.get("timeout_motor_s", 2.0)),
        },
    }


def destrabe_from_config(cfg: Dict[str, Any], tolva: Dict[str, Any]) -> Dict[str, Any]:
    machine = cfg.get("maquina", {}) if isinstance(cfg.get("maquina"), dict) else {}
    base = machine.get("destrabe", {}) if isinstance(machine.get("destrabe"), dict) else {}
    per = tolva.get("destrabe", {}) if isinstance(tolva.get("destrabe"), dict) else {}
    return {
        "enabled": bool(per.get("enabled", base.get("enabled", True))),
        "auto_on_timeout": bool(per.get("auto_on_timeout", base.get("auto_on_timeout", True))),
        "retroceso_s": float(per.get("retroceso_s", base.get("retroceso_s", 1.5))),
        "max_intentos": int(per.get("max_intentos", base.get("max_intentos", 1))),
        "cooldown_s": float(per.get("cooldown_s", base.get("cooldown_s", 2.0))),
    }


def is_event(frame: Dict[str, Any]) -> bool:
    return str(frame.get("dir", "")).lower() == "evt"


def event_type(frame: Dict[str, Any]) -> str:
    return str(frame.get("type", "")).upper()
