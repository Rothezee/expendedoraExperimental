"""Orquestación del ciclo de dispensado y telemetría."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from expendedora.logic.hardware.serial_bridge import SerialBridge
from expendedora.logic.services.machine_state import MachineState
from expendedora.logic.services.tolva_service import TolvaService
from expendedora.persistence.json.config_repository import ConfigRepository
from expendedora.persistence.remote.telemetry_repository import TelemetryRepository

DEFAULT_HEARTBEAT_INTERVALO_S = 600


class DispenserService:
    """
    telemetry_mode en config.operacion:
      - "session" (default): acumulado de sesión al terminar tanda
      - "batch": reservado para delta por tanda (futuro)
    """

    def __init__(
        self,
        machine_state: MachineState,
        tolva_service: TolvaService,
        config_repo: ConfigRepository,
        telemetry_repo: TelemetryRepository,
        *,
        on_state_changed: Optional[Callable[[], None]] = None,
        on_motor_alert: Optional[Callable[[int], None]] = None,
    ) -> None:
        self._machine_state = machine_state
        self._tolva = tolva_service
        self._config_repo = config_repo
        self._telemetry = telemetry_repo
        self._bridge: Optional[SerialBridge] = None
        self._bridge_thread: Optional[threading.Thread] = None
        self._on_state_changed = on_state_changed
        self._on_motor_alert = on_motor_alert

    @property
    def bridge(self) -> Optional[SerialBridge]:
        return self._bridge

    def start(self) -> threading.Thread:
        self._tolva.load_from_config()
        self._bridge = SerialBridge(
            self._machine_state,
            self._tolva,
            on_state_changed=self._on_state_changed,
            on_motor_alert=self._on_motor_alert,
            on_telemetry_done=self.send_telemetry,
            config_repo=self._config_repo,
        )
        self._bridge_thread = threading.Thread(target=self._bridge.run_loop, daemon=True)
        self._bridge_thread.start()
        self._send_heartbeat()
        print("[DISPENSER] Puente serial iniciado en segundo plano")
        return self._bridge_thread

    def stop(self) -> None:
        if self._bridge:
            self._bridge.stop()
            self._bridge = None

    def is_serial_ready(self) -> bool:
        return self._bridge is not None and self._bridge.is_ready()

    def force_reconnect(self) -> bool:
        if self._bridge is None:
            return False
        return self._bridge.force_reconnect()

    def clear_pending(self) -> dict:
        """Vacía buffer y revierte pending lots (atribución para GUI)."""
        revert = self._machine_state.revert_all_pending_lots()
        if self._bridge:
            self._bridge.clear_pending_dispense()
        else:
            self._machine_state.set_fichas_restantes(0, immediate=False)
            self._machine_state.set_motor_activo(False)
            self._machine_state.set_motor_direccion("detenido")
            self._machine_state.persist_now("vaciar_buffer")
        return revert

    def simulate_token(self) -> bool:
        if self._bridge is None:
            return False
        return self._bridge.simulate_token()

    def send_telemetry(self) -> None:
        config = self._config_repo.load()
        body = self._telemetry.build_telemetry_body(
            config,
            fichas=self._machine_state.get_fichas_sesion(),
            dinero=float(self._machine_state.get_r_cuenta()),
        )
        self._telemetry.post_body(body, "telemetria")

    def _send_heartbeat(self) -> None:
        config = self._config_repo.load()
        body = self._telemetry.build_heartbeat_body(config)
        self._telemetry.post_body(body, "heartbeat")
        intervalo = config.get("heartbeat", {}).get("intervalo_s", DEFAULT_HEARTBEAT_INTERVALO_S)
        timer = threading.Timer(intervalo, self._send_heartbeat)
        timer.daemon = True
        timer.start()
