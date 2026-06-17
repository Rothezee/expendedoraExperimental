"""Configuración y estado de tolvas (hoppers)."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from expendedora.persistence.json.config_repository import ConfigRepository
from expendedora.persistence.machine_limits import MAX_MACHINE_HOPPERS

DEFAULT_TOLVAS = [
    {
        "id": 1,
        "nombre": "Tolva 1",
        "motor_pin": 10,
        "motor_pin_rev": 12,
        "sensor_pin": 9,
        "calibracion": {"pulso_min_s": 0.08, "pulso_max_s": 0.2, "timeout_motor_s": 3.0},
    },
]
DEFAULT_SENSOR_BOUNCETIME_MS = 8
DEFAULT_MOTOR_ACTIVE_LOW = True


class TolvaService:
    def __init__(self, config_repo: ConfigRepository) -> None:
        self._config_repo = config_repo
        self._tolvas_lock = threading.Lock()
        self._tolvas: List[dict] = list(DEFAULT_TOLVAS)
        self._tolva_seleccionada_idx = 0
        self._tolvas_trabadas: set = set()
        self._sensor_interrupts_cfg = {"bouncetime_ms": DEFAULT_SENSOR_BOUNCETIME_MS}
        self.bloqueo_emergencia = False
        self._destrabe_request_lock = threading.Lock()
        self._destrabe_requested = {"tolva_id": None, "ts": 0.0}
        self._destrabe_solicitud_ts = 0.0
        self._destrabe_test_token_ts = 0.0
        self.gui_actualizar_funcion = None
        self.gui_alerta_motor_funcion = None

    def load_from_config(self) -> None:
        cfg = self._config_repo.load()
        machine = cfg.get("maquina", {})
        interrupts_cfg = machine.get("sensor_interrupts", {}) if isinstance(machine.get("sensor_interrupts", {}), dict) else {}
        try:
            bouncetime_ms = int(float(interrupts_cfg.get("bouncetime_ms", DEFAULT_SENSOR_BOUNCETIME_MS)))
        except (TypeError, ValueError):
            bouncetime_ms = DEFAULT_SENSOR_BOUNCETIME_MS
        self._sensor_interrupts_cfg = {"bouncetime_ms": max(0, min(1000, bouncetime_ms))}
        hoppers = machine.get("hoppers", DEFAULT_TOLVAS)
        if not isinstance(hoppers, list) or not hoppers:
            hoppers = list(DEFAULT_TOLVAS)
        normalized = []
        for idx, hopper in enumerate(hoppers[:MAX_MACHINE_HOPPERS], start=1):
            if not isinstance(hopper, dict):
                hopper = {}
            fallback = DEFAULT_TOLVAS[(idx - 1) % len(DEFAULT_TOLVAS)]
            motor_pin = int(hopper.get("motor_pin", fallback["motor_pin"]))
            motor_rev = hopper.get("motor_pin_rev", fallback.get("motor_pin_rev"))
            motor_rev_int = int(motor_rev) if motor_rev is not None and str(motor_rev).strip() != "" else None
            if motor_rev_int is not None and motor_pin == motor_rev_int:
                print(f"[TOLVA WARN] motor_pin == motor_pin_rev ({motor_pin}); revisar config.json")
            normalized.append(
                {
                    "id": int(hopper.get("id", fallback["id"])),
                    "nombre": str(hopper.get("nombre", fallback["nombre"])),
                    "motor_pin": motor_pin,
                    "motor_pin_rev": motor_rev_int,
                    "motor_active_low": bool(hopper.get("motor_active_low", DEFAULT_MOTOR_ACTIVE_LOW)),
                    "sensor_pin": int(hopper.get("sensor_pin", fallback["sensor_pin"])),
                    "sensor_bouncetime_ms": (
                        int(float(hopper.get("sensor_bouncetime_ms", self._sensor_interrupts_cfg["bouncetime_ms"])))
                        if str(hopper.get("sensor_bouncetime_ms", "")).strip() != ""
                        else self._sensor_interrupts_cfg["bouncetime_ms"]
                    ),
                    "calibracion": dict(
                        hopper.get("calibracion", fallback.get("calibracion", {}))
                        if isinstance(hopper.get("calibracion", {}), dict)
                        else fallback.get("calibracion", {})
                    ),
                    "destrabe": dict(hopper.get("destrabe", {})) if isinstance(hopper.get("destrabe", {}), dict) else {},
                }
            )
        with self._tolvas_lock:
            self._tolvas = normalized

    def get_tolvas_status(self) -> List[dict]:
        with self._tolvas_lock:
            selected_id = self._tolvas[self._tolva_seleccionada_idx]["id"]
            jammed_ids = set(self._tolvas_trabadas)
            return [
                {
                    "id": tolva["id"],
                    "nombre": tolva["nombre"],
                    "seleccionada": tolva["id"] == selected_id,
                    "trabada": tolva["id"] in jammed_ids,
                }
                for tolva in self._tolvas
            ]

    def seleccionar_tolva(self, offset: int) -> None:
        with self._tolvas_lock:
            self._tolva_seleccionada_idx = (self._tolva_seleccionada_idx + offset) % len(self._tolvas)
        if self.gui_actualizar_funcion:
            try:
                self.gui_actualizar_funcion()
            except Exception as exc:
                print(f"[TOLVA] GUI actualizar: {exc}")

    def solicitar_destrabe(self, tolva_id: Optional[int] = None) -> None:
        try:
            tolva_id_int = int(tolva_id) if tolva_id is not None else None
        except (TypeError, ValueError):
            tolva_id_int = None
        with self._destrabe_request_lock:
            self._destrabe_requested = {"tolva_id": tolva_id_int, "ts": time.time()}
            self._destrabe_solicitud_ts = time.time()
        print(f"[TOLVA] Solicitud destrabe tolva_id={tolva_id_int}")

    def marcar_test_token_destrabe(self) -> None:
        with self._destrabe_request_lock:
            self._destrabe_test_token_ts = time.time()

    def test_token_destrabe_ok(self) -> bool:
        with self._destrabe_request_lock:
            if self._destrabe_solicitud_ts <= 0:
                return False
            return self._destrabe_test_token_ts >= self._destrabe_solicitud_ts

    def destrabe_pendiente(self) -> bool:
        with self._destrabe_request_lock:
            return self._destrabe_requested.get("ts", 0) > 0

    def limpiar_solicitud_destrabe(self) -> None:
        with self._destrabe_request_lock:
            self._destrabe_requested.update({"tolva_id": None, "ts": 0.0})

    def consume_destrabe_request(self) -> Optional[dict]:
        with self._destrabe_request_lock:
            if self._destrabe_requested.get("ts", 0) > 0:
                req = dict(self._destrabe_requested)
                self._destrabe_requested.update({"tolva_id": None, "ts": 0.0})
                return req
        return None

    def desbloquear_motor(self) -> None:
        self.bloqueo_emergencia = False
        print("[TOLVA] Motor desbloqueado por usuario")

    def active_tolva(self, config: Optional[Dict[str, Any]] = None) -> dict:
        with self._tolvas_lock:
            idx = self._tolva_seleccionada_idx
            tolvas = list(self._tolvas)
        if tolvas and 0 <= idx < len(tolvas):
            return dict(tolvas[idx])
        if config:
            hoppers = config.get("maquina", {}).get("hoppers", [])
            if isinstance(hoppers, list) and hoppers:
                return dict(hoppers[0])
        return {"id": 1, "motor_pin": 10, "motor_pin_rev": 12, "sensor_pin": 9}
