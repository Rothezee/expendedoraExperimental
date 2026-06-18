"""Fachada pública de la capa lógica (único punto de acceso desde la interfaz)."""

from __future__ import annotations

import atexit
import threading
from typing import Any, Callable, Dict, Optional

from expendedora.logic.services.counter_service import CounterService
from expendedora.logic.services.dispenser_service import DispenserService
from expendedora.logic.services.machine_state import MachineState
from expendedora.logic.services.network_manager_service import NetworkManagerService
from expendedora.logic.services.recovery_service import RecoveryService
from expendedora.logic.services.session_service import SessionService
from expendedora.logic.services.tolva_service import TolvaService
from expendedora.persistence.json.config_repository import ConfigRepository, DEFAULT_DNI_ADMIN
from expendedora.persistence.json.state_repository import StateRepository
from expendedora.persistence.mysql.report_repository import ReportRepositoryMySQL
from expendedora.persistence.remote.session_api_repository import SessionApiRepository
from expendedora.persistence.db_exception_message import format_db_exception
from expendedora.persistence.remote.telemetry_repository import TelemetryRepository


class AppController:
    def __init__(
        self,
        *,
        config_repo: ConfigRepository,
        state_repo: StateRepository,
        machine_state: MachineState,
        tolva_service: TolvaService,
        recovery_service: RecoveryService,
        dispenser_service: DispenserService,
        telemetry_repo: TelemetryRepository,
        session_api_repo: SessionApiRepository,
        counter_service: CounterService,
        session_service: SessionService,
        network_service: NetworkManagerService,
        report_repo: ReportRepositoryMySQL,
    ) -> None:
        self._config_repo = config_repo
        self._state_repo = state_repo
        self.machine_state = machine_state
        self._tolva = tolva_service
        self._recovery = recovery_service
        self._dispenser = dispenser_service
        self._telemetry = telemetry_repo
        self._session_api = session_api_repo
        self.counter_service = counter_service
        self.session_service = session_service
        self.network_service = network_service
        self.report_repository = report_repo
        self._started = False
        self._on_state_changed: Optional[Callable[[], None]] = None
        self._on_motor_alert: Optional[Callable[[int], None]] = None
        atexit.register(self._atexit_persist)

    @property
    def config_path(self) -> str:
        return self._config_repo.config_path

    @property
    def config_repository(self) -> ConfigRepository:
        """Acceso a config solo vía lógica (la GUI no importa persistencia directamente)."""
        return self._config_repo

    def load_config(self) -> dict:
        return self._config_repo.load()

    def save_config(self, config: dict) -> dict:
        return self._config_repo.save(config)

    def on_state_changed(self, callback: Callable[[], None]) -> None:
        self._on_state_changed = callback
        self._dispenser._on_state_changed = callback
        self.machine_state.gui_update_callback = callback
        self._tolva.gui_actualizar_funcion = callback

    def on_motor_alert(self, callback: Callable[[int], None]) -> None:
        self._on_motor_alert = callback
        self._dispenser._on_motor_alert = callback
        self._tolva.gui_alerta_motor_funcion = callback

    def start(self) -> None:
        if self._started:
            return
        self._tolva.load_from_config()
        self._recovery.recover_and_hydrate()
        if self._on_state_changed:
            self.on_state_changed(self._on_state_changed)
        if self._on_motor_alert:
            self.on_motor_alert(self._on_motor_alert)
        self._dispenser.start()
        self._started = True

    def stop(self) -> None:
        self._flush_persistence()
        self._dispenser.stop()
        self._started = False

    def _flush_persistence(self) -> None:
        self.machine_state.flush_pending()
        try:
            snap = self._state_repo.load_snapshot()
            if snap:
                self._state_repo.save_snapshot(snap, sync_config=self.load_config())
        except Exception as exc:
            print(f"[APP] Aviso persistiendo estado final: {exc}")

    def _atexit_persist(self) -> None:
        try:
            self._flush_persistence()
        except Exception:
            pass

    def get_recovered_state(self) -> Optional[dict]:
        return self._recovery.get_recovered()

    def get_serial_status(self) -> dict:
        ready = self._dispenser.is_serial_ready()
        return {
            "connected": ready,
            "label": "Arduino: OK" if ready else "Arduino: sin conexión",
            "level": "ONLINE" if ready else "OFFLINE",
        }

    def force_reconnect(self) -> bool:
        return self._dispenser.force_reconnect()

    def get_tolvas_status(self) -> list:
        return self._tolva.get_tolvas_status()

    def seleccionar_tolva(self, offset: int) -> None:
        self._tolva.seleccionar_tolva(offset)

    def seleccionar_tolva_siguiente(self) -> None:
        self._tolva.seleccionar_tolva(1)

    def seleccionar_tolva_anterior(self) -> None:
        self._tolva.seleccionar_tolva(-1)

    def solicitar_destrabe(self, tolva_id: int | None = None) -> None:
        self._tolva.solicitar_destrabe(tolva_id)

    def test_token_destrabe_ok(self) -> bool:
        return self._tolva.test_token_destrabe_ok()

    def desbloquear_motor(self) -> None:
        self._tolva.desbloquear_motor()

    def vaciar_buffer(self) -> dict:
        return self._dispenser.clear_pending()

    def simulate_sensor_pulse(self, pin=None) -> bool:
        return self._dispenser.simulate_token()

    def recargar_tolvas_desde_config(self) -> None:
        self._tolva.load_from_config()

    def cargar_fichas_en_cola(self, cantidad: int) -> int:
        self.machine_state.gui_to_core_queue.put({"type": "add_fichas", "cantidad": cantidad})
        self.machine_state.process_gui_commands()
        return self.machine_state.get_fichas_restantes()

    def cargar_promo_en_cola(self, promo_num: int, fichas: int) -> int:
        self.machine_state.gui_to_core_queue.put({"type": "promo", "promo_num": promo_num, "fichas": fichas})
        self.machine_state.process_gui_commands()
        return self.machine_state.get_fichas_restantes()

    def persist_snapshot(
        self,
        *,
        contadores_global: dict,
        contadores_parcial: dict,
        reason: str,
        operacion: dict | None = None,
    ) -> None:
        buf_rest = max(0, int(self.machine_state.get_fichas_restantes()))
        global_sync = dict(contadores_global)
        global_sync["fichas_restantes"] = buf_rest
        self.machine_state.register_gui_counters(global_sync, global_sync, contadores_parcial)
        config = self.load_config()
        config["contadores_global"] = global_sync
        config["contadores_parcial"] = contadores_parcial
        if operacion is not None:
            config["operacion"] = dict(operacion)
        self.machine_state.persist_with_config(reason, config)

    def post_backend_event(
        self,
        *,
        local_path: str,
        cloud_path: str,
        payload: dict,
        descripcion: str,
        retry_without_cashier_id: bool = False,
    ) -> None:
        self._session_api.post_event_async(
            local_path=local_path,
            cloud_path=cloud_path,
            payload=payload,
            descripcion=descripcion,
            retry_without_cashier_id=retry_without_cashier_id,
        )

    @staticmethod
    def format_db_error(exc: Exception) -> str:
        return format_db_exception(exc)
