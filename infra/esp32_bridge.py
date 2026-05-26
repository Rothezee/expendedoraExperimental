"""
Puente PC ↔ ESP32: sincroniza shared_buffer con el firmware.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

import shared_buffer
from infra.config_repository import ConfigRepository
from infra.esp32_protocol import destrabe_from_config, hopper_from_tolva, is_event
from infra.esp32_serial_client import Esp32SerialBackend
from infra.motor_sensor_debug import dbg_log


class Esp32Bridge:
    def __init__(self, core_module: Any) -> None:
        self._core = core_module
        self._backend: Optional[Any] = None
        self._last_sent_target = -1
        self._last_hopper_id = -1
        self._running = False
        self._dispense_armed = False
        self._last_token_ts = 0.0
        self._token_debounce_s = 0.22
        self._last_dbg_omit_ts = 0.0
        self._config_repo = ConfigRepository(getattr(core_module, "config_file", "config.json"))
        self._debug_cfg: Dict[str, Any] = {}
        self._sim_forward_since = 0.0
        self._sim_reverse_until = 0.0
        self._sim_last_unjam_at = 0.0
        self._sim_unjam_attempts = 0
        self._sim_last_remaining = -1
        self._last_reported_session_fichas = 0
        self._reconnect_backoff_s = 5.0
        self._config_applied = False
        self._last_config_attempt_ts = 0.0

    def _dbg(self, category: str, message: str) -> None:
        dbg_log(self._debug_cfg, category, message)

    @property
    def backend(self):
        return self._backend

    def is_ready(self) -> bool:
        return self._backend is not None and self._backend.is_connected()

    def _ensure_config_applied(self, *, force: bool = False) -> bool:
        if not self._backend or not self._backend.is_connected():
            self._config_applied = False
            return False
        now = time.time()
        if not force and self._config_applied:
            return True
        if not force and (now - self._last_config_attempt_ts) < 1.0:
            return False
        self._last_config_attempt_ts = now
        config = self._config_repo.load()
        tolva = self._active_tolva(config)
        destrabe = destrabe_from_config(config, tolva)
        with self._core._tolvas_lock:
            all_tolvas = [dict(t) for t in self._core._tolvas]
        hoppers = [hopper_from_tolva(t) for t in all_tolvas]
        ok = False
        if len(hoppers) > 1 and hasattr(self._backend, "configure_hoppers"):
            ok = self._backend.configure_hoppers(hoppers, destrabe)
            if not ok:
                print("[ESP32 BRIDGE] CONFIG (multi) falló")
        else:
            ok = self._backend.configure_hopper(hopper_from_tolva(tolva), destrabe)
            if not ok:
                print("[ESP32 BRIDGE] CONFIG falló")
        if ok:
            hopper_id = int(hopper_from_tolva(tolva).get("id", 1))
            self._backend.select_hopper(hopper_id)
            self._last_hopper_id = hopper_id
            self._config_applied = True
            self._dbg("CONFIG", f"CONFIG aplicada OK (tolva={hopper_id})")
            return True
        self._config_applied = False
        return False

    def start(self) -> bool:
        config = self._config_repo.load()
        self._debug_cfg = config
        try:
            hw = config.get("hardware", {}) if isinstance(config.get("hardware", {}), dict) else {}
            esp = hw.get("esp32", {}) if isinstance(hw.get("esp32", {}), dict) else {}
            self._token_debounce_s = max(0.08, float(esp.get("token_debounce_s", 0.22)))
        except Exception:
            self._token_debounce_s = 0.22
        if self._backend is None:
            self._backend = Esp32SerialBackend(config)
        if self._backend.is_connected():
            return True
        if not self._backend.connect():
            return False
        tolva = self._active_tolva(config)
        self._ensure_config_applied(force=True)
        hopper_cfg = hopper_from_tolva(tolva)
        hopper_id = int(hopper_cfg.get("id", 1))
        self._dbg(
            "CONFIG",
            f"tolva={hopper_id} motor_pin={hopper_cfg.get('motor_pin')} "
            f"rev_pin={hopper_cfg.get('motor_pin_rev')} sensor_pin={hopper_cfg.get('sensor_pin')} "
            f"active_low={hopper_cfg.get('motor_active_low')}",
        )
        # Armado deriva de fichas pendientes: remaining>0 implica ciclo activo.
        self._dispense_armed = int(shared_buffer.get_fichas_restantes()) > 0
        try:
            if self._dispense_armed:
                remaining = int(shared_buffer.get_fichas_restantes())
                self._backend.set_target(remaining)
                self._dbg("MOTOR", f"Reconexión: SET_TARGET inmediato -> {remaining}")
            else:
                self._backend.stop()
                self._dbg("MOTOR", "STOP enviado al conectar (motor apagado)")
        except Exception as exc:
            self._dbg("MOTOR", f"Sincronización inicial falló: {exc}")
        self._last_sent_target = int(shared_buffer.get_fichas_restantes())
        self._drain_events()
        self._running = True
        self._dbg("BRIDGE", "Conectado; dispensa desarmada hasta cargar fichas")
        print("[ESP32 BRIDGE] Conectado; motor en espera hasta cargar fichas")
        self._reconnect_backoff_s = 5.0
        return True

    def stop(self) -> None:
        self._running = False
        if self._backend:
            try:
                self._backend.stop()
            except Exception:
                pass
            self._backend.disconnect()
        self._backend = None

    def run_loop(self) -> None:
        """Loop principal del puente PC ↔ ESP32."""
        # Mantener loop activo aun sin conexión inicial para reintentos
        # y simulación offline (UI/motor lógico).
        self._running = True
        print("[ESP32 BRIDGE] Iniciando loop de puente serial")
        reconnect_at = time.time()
        while self._running:
            try:
                if self._backend is None or not self._backend.is_connected():
                    now = time.time()
                    if now >= reconnect_at:
                        print("[ESP32 BRIDGE] Reintentando conexión...")
                        if self.start():
                            print("[ESP32 BRIDGE] Reconectado")
                            reconnect_at = 0.0
                        else:
                            self._reconnect_backoff_s = min(30.0, self._reconnect_backoff_s + 5.0)
                            reconnect_at = time.time() + self._reconnect_backoff_s
                            print(
                                f"[ESP32 BRIDGE] Próximo reintento en "
                                f"{self._reconnect_backoff_s:.1f}s"
                            )
                self._loop_iteration()
            except Exception as exc:
                print(f"[ESP32 BRIDGE ERROR] {type(exc).__name__}: {exc}")
                time.sleep(0.1)
            time.sleep(0.005)

    def _drain_events(self) -> None:
        if not self._backend:
            return
        while True:
            batch = self._backend.poll_events()
            if not batch:
                break

    def _loop_iteration(self) -> None:
        fichas_before = int(shared_buffer.get_fichas_restantes())
        shared_buffer.process_gui_commands()
        fichas_after = int(shared_buffer.get_fichas_restantes())
        if fichas_after > fichas_before or shared_buffer.consume_dispense_arm_pending():
            self._dispense_armed = True
            self._dbg("BUFFER", f"Fichas +{max(0, fichas_after - fichas_before)} → armado | pendientes={fichas_after}")
            print(f"[ESP32 BRIDGE] Dispensa armada: {fichas_after} fichas pendientes")
            if fichas_after > 0:
                # Reflejo inmediato al presionar "Expender", sin esperar evento serial.
                self._set_motor_ui_state(True, "adelante")
            else:
                self._set_motor_ui_state(False, "detenido")
        self._handle_destrabe_request()
        self._ensure_config_applied()
        self._simulate_motor_cycle_offline()
        self._sync_target_to_mcu()
        self._sync_hopper_selection()
        if not self._backend:
            return
        for evt in self._backend.poll_events():
            if is_event(evt):
                self._handle_event(evt)

    def _active_tolva(self, config: Dict[str, Any]) -> Dict[str, Any]:
        with self._core._tolvas_lock:
            idx = self._core._tolva_seleccionada_idx
            tolvas = list(self._core._tolvas)
        if not tolvas:
            hoppers = config.get("maquina", {}).get("hoppers", [])
            if isinstance(hoppers, list) and hoppers:
                return dict(hoppers[0])
            return {"id": 1, "motor_pin": 12, "motor_pin_rev": 10, "sensor_pin": 8}
        if 0 <= idx < len(tolvas):
            return dict(tolvas[idx])
        return dict(tolvas[0])

    def _set_motor_ui_state(self, active: bool, direction: str) -> None:
        current_active = bool(shared_buffer.get_motor_activo())
        current_dir = str(shared_buffer.get_motor_direccion() or "detenido").lower()
        direction = str(direction or "detenido").lower()
        if direction not in {"adelante", "atras", "detenido"}:
            direction = "detenido"
        if current_active == bool(active) and current_dir == direction:
            return
        shared_buffer.set_motor_activo(bool(active))
        shared_buffer.set_motor_direccion(direction)
        self._notify_gui()

    def _reset_offline_motor_cycle(self) -> None:
        self._sim_forward_since = 0.0
        self._sim_reverse_until = 0.0
        self._sim_last_unjam_at = 0.0
        self._sim_unjam_attempts = 0
        self._sim_last_remaining = -1

    def _simulate_motor_cycle_offline(self) -> None:
        if self._backend and self._backend.is_connected():
            self._reset_offline_motor_cycle()
            return

        remaining = int(shared_buffer.get_fichas_restantes())
        if remaining <= 0:
            self._reset_offline_motor_cycle()
            self._set_motor_ui_state(False, "detenido")
            return
        if not self._dispense_armed:
            self._set_motor_ui_state(False, "detenido")
            return

        now = time.time()
        config = self._config_repo.load()
        tolva = self._active_tolva(config)
        cal = tolva.get("calibracion", {}) if isinstance(tolva.get("calibracion"), dict) else {}
        timeout_s = float(cal.get("timeout_motor_s", 3.0))
        timeout_s = max(0.2, timeout_s)
        destrabe = destrabe_from_config(config, tolva)
        can_reverse_pin = tolva.get("motor_pin_rev") not in (None, "", -1, "-1")
        retroceso_s = max(0.1, float(destrabe.get("retroceso_s", 1.5)))
        cooldown_s = max(0.0, float(destrabe.get("cooldown_s", 2.0)))
        auto_unjam = bool(destrabe.get("enabled", True) and destrabe.get("auto_on_timeout", True))

        if remaining != self._sim_last_remaining:
            self._sim_last_remaining = remaining
            self._sim_forward_since = now
            self._sim_unjam_attempts = 0
            self._sim_reverse_until = 0.0

        if self._sim_reverse_until > now:
            self._set_motor_ui_state(True, "atras")
            return
        if self._sim_reverse_until > 0.0 and now >= self._sim_reverse_until:
            self._sim_reverse_until = 0.0
            self._sim_forward_since = now
            self._set_motor_ui_state(True, "adelante")
            return

        if self._sim_forward_since <= 0.0:
            self._sim_forward_since = now
        self._set_motor_ui_state(True, "adelante")
        if (now - self._sim_forward_since) < timeout_s:
            return

        can_auto_unjam = (
            auto_unjam
            and can_reverse_pin
            and (now - self._sim_last_unjam_at) >= cooldown_s
        )
        if can_auto_unjam:
            self._sim_unjam_attempts += 1
            self._sim_last_unjam_at = now
            self._sim_reverse_until = now + retroceso_s
            self._sim_forward_since = 0.0
            self._dbg(
                "MOTOR",
                f"SIM OFFLINE UNJAM ciclo={self._sim_unjam_attempts} retroceso_s={retroceso_s}",
            )
            self._set_motor_ui_state(True, "atras")
            return

        # Sin pin de reversa o destrabe deshabilitado: mantener giro hacia adelante.
        # Nunca detener el ciclo offline mientras queden fichas pendientes.
        self._sim_forward_since = now
        self._set_motor_ui_state(True, "adelante")

    def _send_sale_report_if_done(self) -> None:
        restantes = int(shared_buffer.get_fichas_restantes())
        fichas_sesion = int(shared_buffer.get_fichas_expendidas())
        if fichas_sesion <= 0:
            self._last_reported_session_fichas = 0
            return
        if restantes > 0:
            return
        if fichas_sesion == self._last_reported_session_fichas:
            return
        self._last_reported_session_fichas = fichas_sesion
        try:
            threading.Thread(target=self._core.enviar_datos_venta_servidor, daemon=True).start()
        except Exception as exc:
            print(f"[ESP32 BRIDGE] telemetry thread: {exc}")

    def _sync_target_to_mcu(self) -> None:
        if not self._backend or not self._backend.is_connected():
            return
        if self._core.bloqueo_emergencia:
            now = time.time()
            if now - self._last_dbg_omit_ts >= 2.0:
                self._last_dbg_omit_ts = now
                self._dbg("MOTOR", "SET_TARGET omitido (bloqueo_emergencia=ON)")
            return
        remaining = int(shared_buffer.get_fichas_restantes())
        if not self._config_applied:
            if remaining > 0:
                now = time.time()
                if now - self._last_dbg_omit_ts >= 2.0:
                    self._last_dbg_omit_ts = now
                    self._dbg("MOTOR", "SET_TARGET omitido (CONFIG pendiente)")
            return
        self._dispense_armed = remaining > 0
        if remaining != self._last_sent_target:
            self._dbg(
                "MOTOR",
                f"SET_TARGET {self._last_sent_target} → {remaining} "
                f"(remaining>0 => active={remaining > 0})",
            )
            ok = self._backend.set_target(remaining)
            if ok:
                self._last_sent_target = remaining
                if remaining > 0:
                    self._set_motor_ui_state(True, "adelante")
                else:
                    self._dispense_armed = False
                    self._dbg("MOTOR", "Target=0 → desarmado")
                    self._set_motor_ui_state(False, "detenido")
            else:
                self._dbg("MOTOR", f"SET_TARGET {remaining} falló (backend rechazó comando)")

    def _sync_hopper_selection(self) -> None:
        if not self._backend:
            return
        with self._core._tolvas_lock:
            idx = self._core._tolva_seleccionada_idx
            tolvas = list(self._core._tolvas)
        if not tolvas or idx < 0 or idx >= len(tolvas):
            return
        hopper_id = int(tolvas[idx].get("id", 1))
        if hopper_id != self._last_hopper_id:
            self._backend.select_hopper(hopper_id)
            config = self._config_repo.load()
            tolva = dict(tolvas[idx])
            self._config_applied = self._backend.configure_hopper(
                hopper_from_tolva(tolva), destrabe_from_config(config, tolva)
            )
            self._last_hopper_id = hopper_id

    def _active_hopper_id(self) -> int:
        with self._core._tolvas_lock:
            idx = self._core._tolva_seleccionada_idx
            tolvas = list(self._core._tolvas)
        if tolvas and 0 <= idx < len(tolvas):
            return int(tolvas[idx].get("id", 1))
        return 1

    def _apply_token_event(self) -> None:
        hopper_id = self._active_hopper_id()
        remaining_after = max(0, int(shared_buffer.get_fichas_restantes()) - 1)
        self._handle_event(
            {
                "dir": "evt",
                "type": "TOKEN",
                "hopper_id": hopper_id,
                "remaining": remaining_after,
            }
        )

    def simulate_token(self) -> bool:
        """
        Simula una ficha dispensada.
        Con MCU conectado: SYNC target + SIMULATE (el TOKEN llega por serial).
        Sin MCU: aplica TOKEN local en el buffer (modo prueba / desarrollo).
        """
        remaining = int(shared_buffer.get_fichas_restantes())
        if remaining <= 0:
            self._dbg("SENSOR", "SIMULATE omitido: sin fichas pendientes")
            return False
        if self._backend and self.is_ready():
            self._dispense_armed = True
            if remaining != self._last_sent_target:
                self._dbg("MOTOR", f"SIMULATE sync SET_TARGET → {remaining}")
                self._backend.set_target(remaining)
                self._last_sent_target = remaining
            if self._backend.simulate_pulse():
                self._dbg("SENSOR", "SIMULATE enviado al MCU")
                return True
            self._dbg("SENSOR", "SIMULATE serial falló → TOKEN local")
        self._apply_token_event()
        return True

    def _handle_destrabe_request(self) -> None:
        req = None
        with self._core._destrabe_request_lock:
            if self._core._destrabe_requested.get("ts", 0) > 0:
                req = dict(self._core._destrabe_requested)
                self._core._destrabe_requested.update({"tolva_id": None, "ts": 0.0})
        if not req or not self._backend:
            return
        config = self._config_repo.load()
        tolva = self._active_tolva(config)
        destrabe = destrabe_from_config(config, tolva)
        if not destrabe.get("enabled"):
            return
        hopper_id = int(req.get("tolva_id") or tolva.get("id", 1))
        retroceso = float(destrabe.get("retroceso_s", 1.5))
        if self._backend.unjam(hopper_id, retroceso):
            # Durante destrabe el motor gira en reversa.
            self._set_motor_ui_state(True, "atras")

    def _handle_event(self, evt: Dict[str, Any]) -> None:
        etype = str(evt.get("type", "")).upper()
        hopper_id = int(evt.get("hopper_id", evt.get("id", 1)))

        if etype == "MOTOR_ON":
            self._dbg("MOTOR", f"MOTOR_ON tolva={hopper_id} remaining={evt.get('remaining')}")
            self._set_motor_ui_state(True, "adelante")
            return
        if etype == "MOTOR_OFF":
            self._dbg("MOTOR", f"MOTOR_OFF tolva={hopper_id} remaining={evt.get('remaining')}")
            remaining_evt = int(evt.get("remaining", 0) or 0)
            if remaining_evt > 0:
                # En firmware, timeout->destrabe entra con MOTOR_OFF y luego UNJAM_DONE/MOTOR_ON.
                self._set_motor_ui_state(True, "atras")
            else:
                self._set_motor_ui_state(False, "detenido")
            return
        if etype == "SYNC":
            mcu_remaining = int(evt.get("remaining", -1))
            if mcu_remaining >= 0:
                # El PC es la fuente de verdad; SYNC solo alinea el target enviado al MCU.
                self._dbg(
                    "SYNC",
                    f"SYNC mcu_remaining={mcu_remaining} pc_restantes={shared_buffer.get_fichas_restantes()} "
                    f"(no pisa buffer)",
                )
                self._last_sent_target = mcu_remaining
            return
        if etype == "TOKEN":
            now = time.time()
            dt = now - self._last_token_ts
            self._last_token_ts = now
            pc_before = int(shared_buffer.get_fichas_restantes())
            mcu_remaining_raw = evt.get("remaining")
            mcu_remaining = -1
            try:
                if mcu_remaining_raw is not None:
                    mcu_remaining = int(mcu_remaining_raw)
            except Exception:
                mcu_remaining = -1

            token_counted = False
            if mcu_remaining >= 0:
                # MCU manda remaining real tras contar token; usarlo evita drift PC↔MCU.
                new_remaining = max(0, mcu_remaining)
                shared_buffer.set_fichas_restantes(new_remaining, immediate=False)
                token_counted = new_remaining < pc_before
            else:
                if pc_before <= 0:
                    self._dbg("SENSOR", f"TOKEN ignorado (PC ya en 0) mcu_remaining={evt.get('remaining')}")
                    return
                token_counted = bool(shared_buffer.decrementar_fichas_restantes(immediate=False))
                new_remaining = int(shared_buffer.get_fichas_restantes())

            self._last_sent_target = int(shared_buffer.get_fichas_restantes())
            if self._last_sent_target > 0:
                self._sim_forward_since = now
                self._sim_unjam_attempts = 0
                self._sim_last_remaining = self._last_sent_target
                current_dir = str(shared_buffer.get_motor_direccion() or "detenido").lower()
                # Si el token llegó durante destrabe, mantener "atras" hasta UNJAM_DONE/MOTOR_ON.
                if current_dir == "atras":
                    self._set_motor_ui_state(True, "atras")
                else:
                    self._set_motor_ui_state(True, "adelante")
            else:
                # En fallback local no llega RUN_DONE; cerramos estado aquí.
                self._reset_offline_motor_cycle()
                self._set_motor_ui_state(False, "detenido")
            if dt < self._token_debounce_s:
                self._dbg(
                    "SENSOR",
                    f"TOKEN recibido con dt={dt:.3f}s (< debounce PC {self._token_debounce_s:.3f}s), "
                    "pero no se descarta (MCU autoritativo).",
                )
            with self._core._tolvas_lock:
                if hopper_id in self._core._tolvas_trabadas:
                    self._core._tolvas_trabadas.discard(hopper_id)
            if token_counted:
                try:
                    self._core.actualizar_registro("ficha", 1)
                except Exception as exc:
                    print(f"[ESP32 BRIDGE] actualizar_registro: {exc}")
            self._dbg(
                "SENSOR",
                f"TOKEN tolva={hopper_id} mcu_remaining={mcu_remaining_raw} "
                f"pc_before={pc_before} pc_restantes={shared_buffer.get_fichas_restantes()} "
                f"counted={1 if token_counted else 0}",
            )
            print(
                f"[ESP32] TOKEN tolva {hopper_id} | restantes={shared_buffer.get_fichas_restantes()} "
                f"(counted={1 if token_counted else 0})"
            )
            shared_buffer.persist_now("token")
            self._send_sale_report_if_done()
            self._notify_gui()
            return
        if etype == "RUN_DONE":
            self._dbg("MOTOR", f"RUN_DONE remaining={evt.get('remaining')}")
            try:
                shared_buffer.set_fichas_restantes(max(0, int(evt.get("remaining", 0) or 0)), immediate=False)
            except Exception:
                pass
            self._reset_offline_motor_cycle()
            self._set_motor_ui_state(False, "detenido")
            self._last_sent_target = int(evt.get("remaining", 0))
            self._dispense_armed = False
            shared_buffer.persist_now("run_done")
            self._send_sale_report_if_done()
            return
        if etype == "JAM":
            self._dbg("MOTOR", f"JAM tolva={hopper_id} msg={evt.get('message')} remaining={evt.get('remaining')}")
            self._core.bloqueo_emergencia = True
            self._dispense_armed = False
            self._reset_offline_motor_cycle()
            self._set_motor_ui_state(False, "detenido")
            with self._core._tolvas_lock:
                self._core._tolvas_trabadas.add(hopper_id)
            fichas = int(evt.get("remaining", shared_buffer.get_fichas_restantes()))
            print(f"[ESP32] JAM tolva {hopper_id} | pendientes={fichas}")
            if self._core.gui_alerta_motor_funcion:
                try:
                    self._core.gui_alerta_motor_funcion(fichas)
                except Exception as exc:
                    print(f"[ESP32 BRIDGE] alerta GUI: {exc}")
            return
        if etype == "UNJAM_DONE":
            self._dbg("MOTOR", f"UNJAM_DONE tolva={hopper_id}")
            print(f"[ESP32] UNJAM_DONE tolva {hopper_id}")
            # Si destrabó, liberar bloqueo para permitir nuevo SET_TARGET.
            self._core.bloqueo_emergencia = False
            if not shared_buffer.get_motor_activo():
                self._set_motor_ui_state(False, "detenido")
            return
        if etype == "READY":
            self._dbg("BRIDGE", "ESP32 READY (config aplicada)")
            print("[ESP32] READY")
            return
        if etype == "HELLO_ACK":
            return
        if etype == "ERR":
            print(f"[ESP32 ERR] {evt.get('message', evt)}")
            return
        if etype == "PONG":
            return

    def _notify_gui(self) -> None:
        if self._core.gui_actualizar_funcion:
            try:
                self._core.gui_actualizar_funcion()
            except Exception as exc:
                print(f"[ESP32 BRIDGE] GUI callback: {exc}")


_bridge_instance: Optional[Esp32Bridge] = None


def get_bridge() -> Optional[Esp32Bridge]:
    return _bridge_instance


def set_bridge(bridge: Optional[Esp32Bridge]) -> None:
    global _bridge_instance
    _bridge_instance = bridge


def bridge_is_ready() -> bool:
    return _bridge_instance is not None and _bridge_instance.is_ready()
