"""Estado en RAM de la máquina (buffer operativo + ledger de pending lots)."""

from __future__ import annotations

import threading
from queue import Queue
from typing import Any, Callable, Dict, Optional

from expendedora.persistence.json.state_repository import StateRepository
from expendedora.persistence.paths import LEGACY_BUFFER_FILE

STATE_FILE_LEGACY = LEGACY_BUFFER_FILE
BUFFER_PERSISTED_KEYS = StateRepository.buffer_keys()

_PENDING_LOT_KEYS = (
    "fichas_normales",
    "fichas_devolucion",
    "fichas_cambio",
    "fichas_promocion",
    "dinero_ingresado",
    "promo1_contador",
    "promo2_contador",
    "promo3_contador",
)

# Contadores de fichas: paso a paso (TOKEN). Dinero/promo: al inicio de la venta.
_FICHAS_STEP_KEYS = ("fichas_normales", "fichas_devolucion", "fichas_cambio", "fichas_promocion")
_SALE_START_COUNTER_KEYS = ("promo1_contador", "promo2_contador", "promo3_contador")


class _RuntimeState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = {
            "fichas_restantes": 0,
            "fichas_expendidas": 0,
            "fichas_expendidas_sesion": 0,
            "cuenta": 0,
            "r_cuenta": 0,
            "motor_activo": False,
            "motor_direccion": "detenido",
        }

    def get(self, key: str):
        with self._lock:
            return self._data[key]

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value

    def add(self, key: str, value):
        with self._lock:
            self._data[key] += value
            return self._data[key]

    def reset_session(self) -> int:
        with self._lock:
            self._data["fichas_expendidas_sesion"] = 0
            self._data["r_cuenta"] = 0
            return int(self._data["fichas_expendidas"])

    def decrementar_fichas_restantes(self) -> bool:
        with self._lock:
            if self._data["fichas_restantes"] > 0:
                self._data["fichas_restantes"] -= 1
                self._data["fichas_expendidas"] += 1
                self._data["fichas_expendidas_sesion"] += 1
                return True
        return False

    def registrar_fichas_expendidas(self, cantidad: int = 1) -> int:
        try:
            qty = int(cantidad)
        except Exception:
            qty = 0
        if qty <= 0:
            return 0
        with self._lock:
            self._data["fichas_expendidas"] += qty
            self._data["fichas_expendidas_sesion"] += qty
        return qty

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)

    def hydrate_from_buffer_dict(self, buffer: dict) -> None:
        with self._lock:
            for key in BUFFER_PERSISTED_KEYS:
                if key in buffer:
                    self._data[key] = buffer[key]


class MachineState:
    def __init__(self, state_repo: Optional[StateRepository] = None) -> None:
        self._state_repo = state_repo or StateRepository()
        self._runtime = _RuntimeState()
        self._persist_lock = threading.Lock()
        self._persist_timer: Optional[threading.Timer] = None
        self._persist_retry_count = 0
        self._dispense_arm_pending = False
        self._dispense_arm_lock = threading.Lock()
        self._last_gui_contadores: dict | None = None
        self._last_gui_contadores_apertura: dict | None = None
        self._last_gui_contadores_parciales: dict | None = None
        self._pending_lots: list[dict] = []
        self._pending_lots_lock = threading.Lock()
        self._token_attribution_queue: list[dict] = []
        self._token_attribution_lock = threading.Lock()
        self.gui_to_core_queue: Queue = Queue()
        self.gui_update_callback: Callable | None = None

    @staticmethod
    def _empty_pending_lot() -> dict:
        return {
            "fichas": 0,
            "fichas_inicial": 0,
            "fichas_normales": 0,
            "fichas_devolucion": 0,
            "fichas_cambio": 0,
            "fichas_promocion": 0,
            "dinero_ingresado": 0.0,
            "dinero_inicial": 0.0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
        }

    def register_pending_lot(self, fichas: int, **attribution) -> None:
        qty = int(fichas)
        if qty <= 0:
            return
        lot = self._empty_pending_lot()
        lot["fichas"] = qty
        lot["fichas_inicial"] = qty
        dinero = float(attribution.get("dinero_ingresado", 0) or 0)
        lot["dinero_ingresado"] = dinero
        lot["dinero_inicial"] = dinero
        initial: dict = {"fichas": qty, "dinero_ingresado": dinero}
        for key in _PENDING_LOT_KEYS:
            if key == "dinero_ingresado":
                continue
            if key in attribution:
                lot[key] = attribution[key]
                initial[key] = attribution[key]
        lot["_initial"] = initial
        with self._pending_lots_lock:
            self._pending_lots.append(lot)

    @staticmethod
    def _lot_initial_attribution(lot: dict) -> dict:
        """Atribución original de la venta (para anular toda la operación al vaciar buffer)."""
        stored = lot.get("_initial")
        if isinstance(stored, dict):
            return dict(stored)
        fichas_ini = int(lot.get("fichas_inicial") or lot.get("fichas", 0))
        fichas_rem = int(lot.get("fichas", 0))
        consumed = max(0, fichas_ini - fichas_rem)
        initial: dict = {
            "fichas": fichas_ini,
            "dinero_ingresado": float(lot.get("dinero_inicial", lot.get("dinero_ingresado", 0))),
        }
        for key in ("fichas_normales", "fichas_devolucion", "fichas_cambio", "fichas_promocion"):
            remaining = int(lot.get(key, 0))
            if remaining > 0 or consumed > 0:
                initial[key] = remaining + consumed
        for key in _SALE_START_COUNTER_KEYS:
            promo_val = int(lot.get(key, 0))
            if promo_val > 0:
                initial[key] = promo_val
        return initial

    def _consume_one_pending_lot(self) -> dict | None:
        consumed: dict | None = None
        with self._pending_lots_lock:
            while self._pending_lots:
                lot = self._pending_lots[0]
                fichas = int(lot.get("fichas", 0))
                if fichas <= 0:
                    self._pending_lots.pop(0)
                    continue
                fichas_inicial = int(lot.get("fichas_inicial") or fichas or 1)
                consumed = {"fichas": 1}
                for key in _FICHAS_STEP_KEYS:
                    if int(lot.get(key, 0)) > 0:
                        lot[key] = int(lot[key]) - 1
                        consumed[key] = 1
                        break
                dinero_ini = float(lot.get("dinero_inicial", 0))
                if dinero_ini > 0 and fichas_inicial > 0:
                    lot["dinero_ingresado"] = float(lot.get("dinero_ingresado", 0)) - (dinero_ini / fichas_inicial)
                lot["fichas"] = fichas - 1
                if int(lot["fichas"]) <= 0:
                    self._pending_lots.pop(0)
                break
        if consumed:
            with self._token_attribution_lock:
                self._token_attribution_queue.append(consumed)
        return consumed

    def drain_token_attributions(self) -> list[dict]:
        """Atribución por TOKEN para actualizar contadores de fichas en GUI."""
        with self._token_attribution_lock:
            items = list(self._token_attribution_queue)
            self._token_attribution_queue.clear()
            return items

    def consume_pending_lots(self, fichas: int = 1) -> None:
        try:
            qty = int(fichas)
        except Exception:
            qty = 0
        for _ in range(max(0, qty)):
            self._consume_one_pending_lot()

    def revert_all_pending_lots(self) -> dict:
        """Anula venta en buffer: dinero/promo completos; fichas solo las ya dispensadas."""
        totals = self._empty_pending_lot()
        del totals["fichas"]
        del totals["fichas_inicial"]
        del totals["dinero_inicial"]
        fichas_dispensadas = 0
        with self._pending_lots_lock:
            for lot in self._pending_lots:
                initial = self._lot_initial_attribution(lot)
                fichas_ini = int(initial.get("fichas", 0))
                fichas_rem = int(lot.get("fichas", 0))
                fichas_disp = max(0, fichas_ini - fichas_rem)
                fichas_dispensadas += fichas_disp

                totals["dinero_ingresado"] = float(totals.get("dinero_ingresado", 0)) + float(
                    initial.get("dinero_ingresado", 0)
                )
                for key in _SALE_START_COUNTER_KEYS:
                    if key in initial:
                        totals[key] = int(totals.get(key, 0)) + int(initial[key])
                for key in _FICHAS_STEP_KEYS:
                    if fichas_disp > 0 and int(initial.get(key, 0)) > 0:
                        totals[key] = int(totals.get(key, 0)) + fichas_disp
            self._pending_lots.clear()
        totals["fichas_dispensadas"] = fichas_dispensadas
        totals["fichas_hw_revert"] = fichas_dispensadas
        return totals

    def clear_pending_lots(self) -> None:
        with self._pending_lots_lock:
            self._pending_lots.clear()

    def export_pending_lots(self) -> list[dict]:
        with self._pending_lots_lock:
            return [dict(lot) for lot in self._pending_lots]

    def restore_pending_lots(self, lots: list | None) -> None:
        with self._pending_lots_lock:
            self._pending_lots = []
            if not isinstance(lots, list):
                return
            for lot in lots:
                if isinstance(lot, dict):
                    self._pending_lots.append(dict(lot))

    def register_gui_counters(
        self,
        contadores: dict,
        contadores_apertura: dict | None = None,
        contadores_parciales: dict | None = None,
    ) -> None:
        self._last_gui_contadores = dict(contadores) if contadores else None
        self._last_gui_contadores_apertura = dict(contadores_apertura) if contadores_apertura else None
        self._last_gui_contadores_parciales = dict(contadores_parciales) if contadores_parciales else None

    def _buffer_payload(self) -> dict:
        snap = self._runtime.snapshot()
        return {key: snap.get(key, 0) for key in BUFFER_PERSISTED_KEYS}

    def _schedule_state_persist(self, delay_s: float = 0.4) -> None:
        with self._persist_lock:
            if self._persist_timer is not None:
                self._persist_timer.cancel()
            self._persist_timer = threading.Timer(
                max(0.05, float(delay_s)),
                lambda: self.persist_now("debounced"),
            )
            self._persist_timer.daemon = True
            self._persist_timer.start()

    def flush_pending(self) -> None:
        with self._persist_lock:
            if self._persist_timer is not None:
                self._persist_timer.cancel()
                self._persist_timer = None
        self.persist_now("flush_pending")

    def persist_now(self, reason: str = "", *, immediate: bool = True) -> None:
        if not immediate:
            self._schedule_state_persist()
            return
        buf = self._buffer_payload()
        try:
            if self._last_gui_contadores is not None:
                existing = self._state_repo.load_snapshot() or self._state_repo.build_snapshot(reason=reason)
                snap = self._state_repo.build_snapshot(
                    buffer=buf,
                    contadores=self._last_gui_contadores,
                    contadores_apertura=self._last_gui_contadores_apertura or existing.get("contadores_apertura"),
                    contadores_parciales=self._last_gui_contadores_parciales or existing.get("contadores_parciales"),
                    pending_lots=self.export_pending_lots(),
                    reason=reason,
                )
                self._state_repo.save_snapshot(snap)
            else:
                self._state_repo.save_buffer_only(buf, reason=reason)
            self._persist_retry_count = 0
        except (PermissionError, OSError) as exc:
            self._persist_retry_count = min(self._persist_retry_count + 1, 6)
            retry_delay = min(5.0, 0.4 * (2 ** (self._persist_retry_count - 1)))
            print(
                f"[STATE WARN] Persistencia diferida ({reason or 'sin_motivo'}): {exc}. "
                f"Reintento en {retry_delay:.1f}s"
            )
            self._schedule_state_persist(retry_delay)

    def persist_with_config(self, reason: str, config: dict) -> None:
        buf = self._buffer_payload()
        snap = self._state_repo.build_snapshot(
            buffer=buf,
            contadores_global=config.get("contadores_global"),
            contadores_parcial=config.get("contadores_parcial"),
            reason=reason,
        )
        self._state_repo.save_snapshot(snap, sync_config=config)

    def hydrate_from_recovery(self, buffer: dict) -> None:
        self._runtime.hydrate_from_buffer_dict(buffer or self._state_repo.default_buffer())

    def get_fichas_restantes(self) -> int:
        return int(self._runtime.get("fichas_restantes"))

    def get_fichas_sesion(self) -> int:
        return int(self._runtime.get("fichas_expendidas_sesion"))

    def get_fichas_acumuladas(self) -> int:
        return int(self._runtime.get("fichas_expendidas"))

    def set_fichas_restantes(self, value, *, immediate: bool = True) -> None:
        self._runtime.set("fichas_restantes", value)
        if immediate:
            self.persist_now("set_fichas_restantes")
        else:
            self._schedule_state_persist()

    def set_fichas_acumuladas(self, value, *, immediate: bool = True) -> None:
        self._runtime.set("fichas_expendidas", value)
        if immediate:
            self.persist_now("set_fichas_acumuladas")
        else:
            self._schedule_state_persist()

    def reset_fichas_sesion(self, *, immediate: bool = True) -> None:
        total = self._runtime.reset_session()
        self.clear_pending_lots()
        print(f"[STATE] Sesión reiniciada. Total acumulado HW: {total}")
        if immediate:
            self.persist_now("reset_sesion")
        else:
            self._schedule_state_persist()

    def consume_dispense_arm_pending(self) -> bool:
        with self._dispense_arm_lock:
            pending = self._dispense_arm_pending
            self._dispense_arm_pending = False
            return pending

    def _mark_dispense_arm_pending(self) -> None:
        with self._dispense_arm_lock:
            self._dispense_arm_pending = True

    def agregar_fichas(self, cantidad, *, immediate: bool = True) -> int:
        new_value = self._runtime.add("fichas_restantes", cantidad)
        if immediate:
            self.persist_now("add_fichas")
        else:
            self._schedule_state_persist()
        return int(new_value)

    def decrementar_fichas_restantes(self, *, immediate: bool = True) -> bool:
        ok = self._runtime.decrementar_fichas_restantes()
        if ok:
            if immediate:
                self.persist_now("token")
            else:
                self._schedule_state_persist()
        return ok

    def registrar_fichas_expendidas(self, cantidad: int = 1, *, immediate: bool = True) -> int:
        applied = self._runtime.registrar_fichas_expendidas(cantidad)
        if applied > 0:
            if immediate:
                self.persist_now("token")
            else:
                self._schedule_state_persist()
        return applied

    def revert_fichas_sesion_hw(self, cantidad: int, *, immediate: bool = True) -> None:
        """Resta fichas ya contadas por TOKEN al anular una venta completa."""
        qty = max(0, int(cantidad))
        if qty <= 0:
            return
        snap = self._runtime.snapshot()
        sesion = max(0, int(snap.get("fichas_expendidas_sesion", 0)) - qty)
        acum = max(0, int(snap.get("fichas_expendidas", 0)) - qty)
        self._runtime.set("fichas_expendidas_sesion", sesion)
        self._runtime.set("fichas_expendidas", acum)
        if immediate:
            self.persist_now("revert_fichas_sesion")
        else:
            self._schedule_state_persist()

    def get_motor_activo(self) -> bool:
        return bool(self._runtime.get("motor_activo"))

    def set_motor_activo(self, value) -> None:
        self._runtime.set("motor_activo", bool(value))

    def get_motor_direccion(self) -> str:
        return str(self._runtime.get("motor_direccion") or "detenido")

    def set_motor_direccion(self, value) -> None:
        value_norm = str(value or "detenido").strip().lower()
        if value_norm not in {"adelante", "atras", "detenido"}:
            value_norm = "detenido"
        self._runtime.set("motor_direccion", value_norm)

    def get_cuenta(self):
        return self._runtime.get("cuenta")

    def set_cuenta(self, value, *, immediate: bool = True) -> None:
        self._runtime.set("cuenta", value)
        if immediate:
            self.persist_now("set_cuenta")
        else:
            self._schedule_state_persist()

    def add_to_cuenta(self, value, *, immediate: bool = True) -> None:
        self._runtime.add("cuenta", value)
        if immediate:
            self.persist_now("add_cuenta")
        else:
            self._schedule_state_persist()

    def get_r_cuenta(self):
        return self._runtime.get("r_cuenta")

    def set_r_cuenta(self, value, *, immediate: bool = True) -> None:
        self._runtime.set("r_cuenta", value)
        if immediate:
            self.persist_now("set_r_cuenta")
        else:
            self._schedule_state_persist()

    def process_gui_commands(self) -> None:
        comando_procesado = False
        while not self.gui_to_core_queue.empty():
            command = self.gui_to_core_queue.get()
            comando_procesado = True
            if command["type"] == "add_fichas":
                self.agregar_fichas(command["cantidad"])
                self._mark_dispense_arm_pending()
                print(f"[LOGIC] Fichas agregadas: {command['cantidad']} | Total: {self.get_fichas_restantes()}")
            elif command["type"] == "promo":
                self.agregar_fichas(command["fichas"])
                self._mark_dispense_arm_pending()
                print(
                    f"[LOGIC] Promo {command['promo_num']} activada: {command['fichas']} fichas | "
                    f"Total: {self.get_fichas_restantes()}"
                )
            elif command["type"] == "reset_sesion":
                self.reset_fichas_sesion()
        if comando_procesado and self.gui_update_callback:
            try:
                self.gui_update_callback()
            except Exception as exc:
                print(f"[ERROR] Callback GUI falló: {exc}")
