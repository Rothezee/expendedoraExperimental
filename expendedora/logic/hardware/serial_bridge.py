"""
Puente PC ↔ Arduino (serial): sincroniza MachineState con el firmware.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from expendedora.logic.hardware.protocol import destrabe_from_config, hopper_from_tolva, is_event
from expendedora.logic.hardware.serial_client import SerialBackend
from expendedora.logic.hardware.motor_sensor_debug import dbg_log
from expendedora.logic.services.machine_state import MachineState
from expendedora.persistence.json.config_repository import ConfigRepository


class SerialBridge:
    def __init__(
        self,
        machine_state: MachineState,
        tolva_host: Any,
        *,
        on_state_changed: Optional[Callable[[], None]] = None,
        on_motor_alert: Optional[Callable[[int], None]] = None,
        on_telemetry_done: Optional[Callable[[], None]] = None,
        config_repo: Optional[ConfigRepository] = None,
    ) -> None:
        self._machine_state = machine_state
        self._tolva_host = tolva_host
        self._backend: Optional[Any] = None
        self._last_sent_target = -1
        self._last_hopper_id = -1
        self._running = False
        self._dispense_armed = False
        self._last_token_ts = 0.0
        self._token_debounce_s = 0.22
        self._last_dbg_omit_ts = 0.0
        self._on_state_changed = on_state_changed
        self._on_motor_alert = on_motor_alert
        self._on_telemetry_done = on_telemetry_done
        self._config_repo = config_repo or ConfigRepository()
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
        self._last_rx_ts = 0.0
        self._last_cmd_ts = 0.0
        self._rx_stale_timeout_s = 15.0
        self._last_mcu_remaining = -1
        self._last_resync_ts = 0.0
        self._resync_interval_s = 3.0
        self._mcu_target_confirmed = False
        self._last_target_push_ts = 0.0
        self._reconnect_backoff_pending_s = 2.0
        self._last_watchdog_ping_ts = 0.0
        self._destrabe_test_en_curso = False

    def _wire_backend_callbacks(self) -> None:
        if self._backend is None:
            return
        if hasattr(self._backend, "set_serial_activity_callback"):
            self._backend.set_serial_activity_callback(self._touch_rx)

    def _dbg(self, category: str, message: str) -> None:
        dbg_log(self._debug_cfg, category, message)

    @property
    def backend(self):
        return self._backend

    def is_ready(self) -> bool:
        return self._backend is not None and self._backend.is_connected()

    def _touch_rx(self) -> None:
        self._last_rx_ts = time.time()

    def _touch_cmd(self) -> None:
        self._last_cmd_ts = time.time()

    def clear_pending_dispense(self) -> None:
        """Vacía fichas pendientes en PC y detiene el MCU (contadores: revertir en GUI)."""
        self._machine_state.set_fichas_restantes(0, immediate=False)
        self._machine_state.set_motor_activo(False)
        self._machine_state.set_motor_direccion("detenido")
        self._dispense_armed = False
        self._last_sent_target = 0
        self._last_mcu_remaining = 0
        self._mcu_target_confirmed = True
        self._reset_offline_motor_cycle()
        self._tolva_host.bloqueo_emergencia = False
        with self._tolva_host._tolvas_lock:
            self._tolva_host._tolvas_trabadas.clear()
        if self._backend and self._backend.is_connected():
            try:
                self._touch_cmd()
                self._backend.stop()
                self._backend.set_target(0)
            except Exception as exc:
                print(f"[ARDUINO] clear_pending_dispense MCU: {exc}")
        self._set_motor_ui_state(False, "detenido")
        self._machine_state.persist_now("vaciar_buffer")
        self._notify_gui()

    def _pending_fichas(self) -> int:
        return max(0, int(self._machine_state.get_fichas_restantes()))

    def _reconnect_backoff_for_state(self) -> float:
        if self._pending_fichas() > 0:
            return self._reconnect_backoff_pending_s
        return self._reconnect_backoff_s

    def _recover_pending_dispense(self, *, reason: str) -> bool:
        """Reenvía venta pendiente al MCU (sin vaciar buffer PC)."""
        pending = self._pending_fichas()
        if pending <= 0:
            return False
        if self._tolva_host.bloqueo_emergencia:
            return False
        self._dispense_armed = True
        self._last_sent_target = -1
        self._last_mcu_remaining = -1
        self._mcu_target_confirmed = False
        print(
            f"[ARDUINO] Recuperando venta pendiente ({pending} fichas) [{reason}]"
        )
        if not self.is_ready():
            return False
        self._ensure_config_applied(force=False)
        ok = False
        for _ in range(3):
            if self._push_pc_target_to_mcu(force=True):
                ok = True
                break
            time.sleep(0.12)
        if ok:
            self._set_motor_ui_state(True, "adelante")
        return ok

    def _ensure_pending_dispense_armed(self) -> None:
        pending = self._pending_fichas()
        if pending <= 0:
            return
        if not self._dispense_armed:
            self._dispense_armed = True
            self._mcu_target_confirmed = False
            self._last_sent_target = -1
            print(
                f"[ARDUINO] Venta pendiente en buffer ({pending} fichas); "
                "rearmando dispensador"
            )
            self._set_motor_ui_state(True, "adelante")

    def force_reconnect(self) -> bool:
        if self._backend:
            try:
                self._backend.disconnect()
            except Exception as exc:
                print(f"[ARDUINO] force_reconnect disconnect: {exc}")
        self._config_applied = False
        self._mcu_target_confirmed = False
        self._reconnect_backoff_s = self._reconnect_backoff_for_state()
        ok = self.start()
        if ok:
            print("[ARDUINO] Reconexión forzada OK")
        else:
            print("[ARDUINO] Reconexión forzada falló")
        return ok

    def _check_connection_health(self) -> None:
        pending = self._pending_fichas()
        if not self.is_ready():
            return
        now = time.time()
        if self._last_rx_ts <= 0:
            return
        stale_limit = 8.0 if pending > 0 else self._rx_stale_timeout_s
        stale = (now - self._last_rx_ts) > stale_limit
        if not stale:
            return
        recent_cmd = self._last_cmd_ts > 0 and (now - self._last_cmd_ts) < 20.0
        if not (pending > 0 or recent_cmd):
            return
        if now - self._last_watchdog_ping_ts < 2.0:
            return
        self._last_watchdog_ping_ts = now
        ping_ok = False
        if self._backend and hasattr(self._backend, "ping_wait_pong"):
            ping_ok = self._backend.ping_wait_pong(1.0)
        if ping_ok:
            self._touch_rx()
            self._dbg(
                "BRIDGE",
                f"Watchdog: sin eventos JSON >{stale_limit:.0f}s pero PONG OK (link vivo)",
            )
            return
        print(
            f"[ARDUINO] Watchdog: link muerto (sin RX >{stale_limit:.0f}s, PING sin PONG) "
            f"pendientes={pending}; forzando reconexión"
        )
        self.force_reconnect()

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
        with self._tolva_host._tolvas_lock:
            all_tolvas = [dict(t) for t in self._tolva_host._tolvas]
        hoppers = [hopper_from_tolva(t) for t in all_tolvas]
        ok = False
        if len(hoppers) > 1 and hasattr(self._backend, "configure_hoppers"):
            ok = self._backend.configure_hoppers(hoppers, destrabe)
            if not ok:
                print("[ARDUINO] CONFIG (multi) falló")
        else:
            ok = self._backend.configure_hopper(hopper_from_tolva(tolva), destrabe)
            if not ok:
                print("[ARDUINO] CONFIG falló")
        if ok:
            hopper_id = int(hopper_from_tolva(tolva).get("id", 1))
            self._backend.select_hopper(hopper_id)
            self._last_hopper_id = hopper_id
            self._config_applied = True
            self._dbg("CONFIG", f"CONFIG aplicada OK (tolva={hopper_id})")
            # CONFIG en firmware pone fichasRestantes=0; re-alinear con buffer PC.
            self._last_mcu_remaining = 0
            pending = int(self._machine_state.get_fichas_restantes())
            if pending > 0:
                self._last_sent_target = -1
                self._push_pc_target_to_mcu(force=True)
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
            if esp.get("debug_motor_sensor"):
                print("[ARDUINO] Depuración motor/sensor ACTIVA (consola + CONFIG debug=true al MCU)")
        except Exception:
            self._token_debounce_s = 0.22
        if self._backend is None:
            self._backend = SerialBackend(config)
        self._wire_backend_callbacks()
        if self._backend.is_connected():
            if self._pending_fichas() > 0:
                self._recover_pending_dispense(reason="conexion_activa")
            return True
        if not self._backend.connect():
            return False
        self._wire_backend_callbacks()
        tolva = self._active_tolva(config)
        self._ensure_config_applied(force=True)
        hopper_cfg = hopper_from_tolva(tolva)
        hopper_id = int(hopper_cfg.get("id", 1))
        self._dbg(
            "CONFIG",
            f"tolva={hopper_id} motor_pin={hopper_cfg.get('motor_pin')} "
            f"rev_pin={hopper_cfg.get('motor_pin_rev')} sensor_pin={hopper_cfg.get('sensor_pin')} "
            f"active_low={hopper_cfg.get('motor_active_low')} "
            f"sensor_blocked_high={hopper_cfg.get('sensor_blocked_high')}",
        )
        # Armado deriva de fichas pendientes: remaining>0 implica ciclo activo.
        self._dispense_armed = self._pending_fichas() > 0
        try:
            if self._dispense_armed:
                self._recover_pending_dispense(reason="reconexion")
            elif not self._tolva_host.destrabe_pendiente():
                if self._backend.stop():
                    self._touch_cmd()
                self._dbg("MOTOR", "STOP enviado al conectar (motor apagado)")
                self._last_sent_target = 0
                self._last_mcu_remaining = 0
                self._mcu_target_confirmed = True
            else:
                self._dbg("MOTOR", "STOP omitido al conectar (destrabe pendiente)")
        except Exception as exc:
            self._dbg("MOTOR", f"Sincronización inicial falló: {exc}")
        self._drain_events()
        self._touch_rx()
        self._running = True
        pending = self._pending_fichas()
        if pending > 0:
            self._dbg("BRIDGE", f"Conectado; venta pendiente={pending} fichas (recuperación activa)")
            print(f"[ARDUINO] Conectado; reanudando venta pendiente ({pending} fichas)")
        else:
            self._dbg("BRIDGE", "Conectado; sin fichas pendientes")
            print("[ARDUINO] Conectado; motor en espera")
        self._reconnect_backoff_s = self._reconnect_backoff_for_state()
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
        """Loop principal del puente PC ↔ Arduino."""
        # Mantener loop activo aun sin conexión inicial para reintentos
        # y simulación offline (UI/motor lógico).
        self._running = True
        print("[ARDUINO] Iniciando loop de puente serial")
        reconnect_at = 0.0 if self._pending_fichas() > 0 else time.time()
        while self._running:
            try:
                if self._backend is None or not self._backend.is_connected():
                    now = time.time()
                    if now >= reconnect_at:
                        print("[ARDUINO] Reintentando conexión...")
                        if self.start():
                            print("[ARDUINO] Reconectado")
                            reconnect_at = 0.0
                        else:
                            step = self._reconnect_backoff_for_state()
                            pending = self._pending_fichas()
                            if pending > 0:
                                self._reconnect_backoff_s = step
                            else:
                                self._reconnect_backoff_s = min(30.0, self._reconnect_backoff_s + step)
                            reconnect_at = time.time() + self._reconnect_backoff_s
                            print(
                                f"[ARDUINO] Próximo reintento en "
                                f"{self._reconnect_backoff_s:.1f}s"
                                + (f" (venta pendiente: {pending} fichas)" if pending > 0 else "")
                            )
                            if self._reconnect_backoff_s >= 30.0:
                                print(
                                    "[ARDUINO] Reconexión automática activa; "
                                    "probá Reconectar en el header o revisá el puerto COM"
                                )
                self._check_connection_health()
                self._loop_iteration()
            except Exception as exc:
                print(f"[ARDUINO ERROR] {type(exc).__name__}: {exc}")
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
        self._ensure_pending_dispense_armed()
        fichas_before = int(self._machine_state.get_fichas_restantes())
        self._machine_state.process_gui_commands()
        fichas_after = int(self._machine_state.get_fichas_restantes())
        if fichas_after > fichas_before or self._machine_state.consume_dispense_arm_pending():
            self._dispense_armed = True
            self._dbg("BUFFER", f"Fichas +{max(0, fichas_after - fichas_before)} → armado | pendientes={fichas_after}")
            print(f"[ARDUINO] Dispensa armada: {fichas_after} fichas pendientes")
            if fichas_after > 0:
                # Reflejo inmediato al presionar "Expender", sin esperar evento serial.
                self._set_motor_ui_state(True, "adelante")
            else:
                self._set_motor_ui_state(False, "detenido")
        self._ensure_config_applied()
        self._handle_destrabe_request()
        self._simulate_motor_cycle_offline()
        self._maybe_periodic_resync()
        self._sync_target_to_mcu()
        self._sync_hopper_selection()
        if not self._backend:
            return
        for evt in self._backend.poll_events():
            if is_event(evt):
                self._touch_rx()
                self._handle_event(evt)

    def _active_tolva(self, config: Dict[str, Any]) -> Dict[str, Any]:
        with self._tolva_host._tolvas_lock:
            idx = self._tolva_host._tolva_seleccionada_idx
            tolvas = list(self._tolva_host._tolvas)
        if not tolvas:
            hoppers = config.get("maquina", {}).get("hoppers", [])
            if isinstance(hoppers, list) and hoppers:
                return dict(hoppers[0])
            return {"id": 1, "motor_pin": 10, "motor_pin_rev": 12, "sensor_pin": 9}
        if 0 <= idx < len(tolvas):
            return dict(tolvas[idx])
        return dict(tolvas[0])

    def _set_motor_ui_state(self, active: bool, direction: str) -> None:
        current_active = bool(self._machine_state.get_motor_activo())
        current_dir = str(self._machine_state.get_motor_direccion() or "detenido").lower()
        direction = str(direction or "detenido").lower()
        if direction not in {"adelante", "atras", "detenido"}:
            direction = "detenido"
        if current_active == bool(active) and current_dir == direction:
            return
        self._machine_state.set_motor_activo(bool(active))
        self._machine_state.set_motor_direccion(direction)
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

        remaining = int(self._machine_state.get_fichas_restantes())
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
        restantes = int(self._machine_state.get_fichas_restantes())
        fichas_sesion = int(self._machine_state.get_fichas_sesion())
        # Enviar solo cuando la tanda termina (restantes == 0).
        if restantes != 0:
            if fichas_sesion <= 0:
                self._last_reported_session_fichas = 0
            return
        if fichas_sesion <= 0:
            return
        if fichas_sesion == self._last_reported_session_fichas:
            return
        self._last_reported_session_fichas = fichas_sesion
        try:
            if self._on_telemetry_done:
                threading.Thread(target=self._on_telemetry_done, daemon=True).start()
        except Exception as exc:
            print(f"[ARDUINO] telemetry thread: {exc}")

    def _push_pc_target_to_mcu(self, *, force: bool = False) -> bool:
        """Envía al MCU el buffer PC (fuente de verdad para el operador)."""
        if not self._backend or not self._backend.is_connected():
            return False
        if self._tolva_host.bloqueo_emergencia:
            return False
        if not self._config_applied:
            return False
        remaining = int(self._machine_state.get_fichas_restantes())
        self._dispense_armed = remaining > 0
        if not force and remaining == self._last_sent_target:
            return True
        self._dbg(
            "MOTOR",
            f"SET_TARGET {self._last_sent_target} → {remaining} "
            f"(pc_autoritativo active={remaining > 0})",
        )
        ok = self._backend.set_target(remaining)
        if ok:
            self._touch_cmd()
            self._last_sent_target = remaining
            self._last_target_push_ts = time.time()
            self._mcu_target_confirmed = False
            if remaining > 0:
                self._set_motor_ui_state(True, "adelante")
            else:
                self._dispense_armed = False
                self._dbg("MOTOR", "Target=0 → desarmado")
                self._set_motor_ui_state(False, "detenido")
                self._mcu_target_confirmed = True
            return True
        self._dbg("MOTOR", f"SET_TARGET {remaining} falló (backend rechazó comando)")
        return False

    def _reconcile_with_mcu(self, mcu_remaining: int, *, source: str) -> None:
        """Detecta desfase MCU↔PC y reenvía SET_TARGET desde el buffer PC."""
        pc = int(self._machine_state.get_fichas_restantes())
        self._last_mcu_remaining = mcu_remaining
        if mcu_remaining == pc:
            self._last_sent_target = pc
            self._mcu_target_confirmed = True
            return
        self._dbg(
            "SYNC",
            f"Desfase [{source}] mcu={mcu_remaining} pc={pc} -> SET_TARGET({pc})",
        )
        print(
            f"[ARDUINO] Desfase contador ({source}): MCU={mcu_remaining} vs PC={pc}; "
            "re-sincronizando desde PC"
        )
        self._last_sent_target = -1
        self._push_pc_target_to_mcu(force=True)
        self._last_resync_ts = time.time()

    def _maybe_periodic_resync(self) -> None:
        if not self.is_ready() or not self._config_applied:
            return
        pc = self._pending_fichas()
        if pc <= 0 or self._tolva_host.bloqueo_emergencia:
            return
        now = time.time()
        interval = self._resync_interval_s if self._mcu_target_confirmed else 2.0
        if now - self._last_resync_ts < interval:
            return
        self._last_resync_ts = now
        if self._last_mcu_remaining >= 0 and self._last_mcu_remaining != pc:
            self._reconcile_with_mcu(self._last_mcu_remaining, source="periodic")
        elif not self._mcu_target_confirmed:
            since_push = now - self._last_target_push_ts if self._last_target_push_ts > 0 else interval + 1
            if since_push >= interval:
                self._recover_pending_dispense(reason="reintento_periodico")
        elif self._last_sent_target != pc:
            self._push_pc_target_to_mcu(force=True)

    def _sync_target_to_mcu(self) -> None:
        if not self._backend or not self._backend.is_connected():
            return
        if self._tolva_host.bloqueo_emergencia:
            now = time.time()
            if now - self._last_dbg_omit_ts >= 2.0:
                self._last_dbg_omit_ts = now
                self._dbg("MOTOR", "SET_TARGET omitido (bloqueo_emergencia=ON)")
            return
        remaining = int(self._machine_state.get_fichas_restantes())
        if not self._config_applied:
            if remaining > 0:
                now = time.time()
                if now - self._last_dbg_omit_ts >= 2.0:
                    self._last_dbg_omit_ts = now
                    self._dbg("MOTOR", "SET_TARGET omitido (CONFIG pendiente)")
            return
        self._push_pc_target_to_mcu(force=False)

    def _sync_hopper_selection(self) -> None:
        if not self._backend:
            return
        with self._tolva_host._tolvas_lock:
            idx = self._tolva_host._tolva_seleccionada_idx
            tolvas = list(self._tolva_host._tolvas)
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
            if self._config_applied:
                self._last_mcu_remaining = 0
                if int(self._machine_state.get_fichas_restantes()) > 0:
                    self._last_sent_target = -1
                    self._push_pc_target_to_mcu(force=True)

    def _active_hopper_id(self) -> int:
        with self._tolva_host._tolvas_lock:
            idx = self._tolva_host._tolva_seleccionada_idx
            tolvas = list(self._tolva_host._tolvas)
        if tolvas and 0 <= idx < len(tolvas):
            return int(tolvas[idx].get("id", 1))
        return 1

    def _apply_token_event(self) -> None:
        hopper_id = self._active_hopper_id()
        remaining_after = max(0, int(self._machine_state.get_fichas_restantes()) - 1)
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
        remaining = int(self._machine_state.get_fichas_restantes())
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
        if not self._tolva_host.destrabe_pendiente():
            return
        if not self.is_ready() or not self._config_applied:
            return
        if self._destrabe_test_en_curso:
            return
        req = None
        with self._tolva_host._destrabe_request_lock:
            if self._tolva_host._destrabe_requested.get("ts", 0) > 0:
                req = dict(self._tolva_host._destrabe_requested)
        if not req or not self._backend:
            return
        config = self._config_repo.load()
        tolva = self._active_tolva(config)
        destrabe = destrabe_from_config(config, tolva)
        if not destrabe.get("enabled"):
            self._tolva_host.limpiar_solicitud_destrabe()
            return
        if hasattr(self._backend, "test_dispense"):
            if self._backend.test_dispense():
                self._tolva_host.limpiar_solicitud_destrabe()
                self._destrabe_test_en_curso = True
                self._touch_cmd()
                self._set_motor_ui_state(True, "adelante")
                print("[ARDUINO] Destrabe de prueba enviado (hasta 3 intentos adelante+reversa)")
            else:
                print("[ARDUINO] Destrabe de prueba: falló envío TEST_DISPENSE (reintentará)")
        else:
            hopper_id = int(req.get("tolva_id") or tolva.get("id", 1))
            retroceso = float(destrabe.get("retroceso_s", 1.5))
            if self._backend.unjam(hopper_id, retroceso):
                self._tolva_host.limpiar_solicitud_destrabe()
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
                pc = int(self._machine_state.get_fichas_restantes())
                self._dbg(
                    "SYNC",
                    f"SYNC mcu={mcu_remaining} pc={pc} (PC autoritativo, no pisa buffer)",
                )
                if mcu_remaining != pc:
                    self._reconcile_with_mcu(mcu_remaining, source="SYNC")
                else:
                    self._last_mcu_remaining = mcu_remaining
                    self._last_sent_target = pc
                    self._mcu_target_confirmed = True
            return
        if etype == "TEST_TOKEN":
            self._destrabe_test_en_curso = False
            self._dbg("SENSOR", f"TEST_TOKEN recibido (tolva={hopper_id}). Ficha ignorada para contadores.")
            print(f"[ARDUINO] TEST_TOKEN tolva {hopper_id} | Ficha de prueba dispensada (no contada)")
            if hasattr(self._tolva_host, "marcar_test_token_destrabe"):
                self._tolva_host.marcar_test_token_destrabe()
            self._tolva_host.bloqueo_emergencia = False
            with self._tolva_host._tolvas_lock:
                if hopper_id in self._tolva_host._tolvas_trabadas:
                    self._tolva_host._tolvas_trabadas.discard(hopper_id)
            self._set_motor_ui_state(False, "detenido")
            self._notify_gui()
            return
        if etype == "TOKEN":
            now = time.time()
            dt = now - self._last_token_ts
            self._last_token_ts = now
            pc_before = int(self._machine_state.get_fichas_restantes())
            mcu_remaining_raw = evt.get("remaining")
            mcu_remaining = -1
            try:
                if mcu_remaining_raw is not None:
                    mcu_remaining = int(mcu_remaining_raw)
            except Exception:
                mcu_remaining = -1

            if pc_before <= 0:
                self._dbg(
                    "SENSOR",
                    f"TOKEN ignorado (PC ya en 0) mcu_remaining={mcu_remaining_raw}",
                )
                if mcu_remaining > 0:
                    self._reconcile_with_mcu(mcu_remaining, source="TOKEN_pc0")
                return

            # PC es fuente de verdad: cada TOKEN = 1 ficha; el MCU se re-alinea si difiere.
            new_remaining = pc_before - 1
            self._machine_state.set_fichas_restantes(new_remaining, immediate=False)
            self._machine_state.registrar_fichas_expendidas(1, immediate=False)
            self._machine_state.consume_pending_lots(1)
            token_counted = True
            counted_delta = 1

            if mcu_remaining >= 0 and mcu_remaining != new_remaining:
                self._reconcile_with_mcu(mcu_remaining, source="TOKEN")
            else:
                if mcu_remaining >= 0:
                    self._last_mcu_remaining = mcu_remaining
                self._last_sent_target = new_remaining
                if mcu_remaining < 0 or mcu_remaining == new_remaining:
                    self._mcu_target_confirmed = True
            if new_remaining <= 0:
                self._machine_state.clear_pending_lots()
                self._dispense_armed = False
                self._reset_offline_motor_cycle()
                self._set_motor_ui_state(False, "detenido")
            elif self._last_sent_target > 0:
                self._sim_forward_since = now
                self._sim_unjam_attempts = 0
                self._sim_last_remaining = self._last_sent_target
                current_dir = str(self._machine_state.get_motor_direccion() or "detenido").lower()
                if current_dir == "atras":
                    self._set_motor_ui_state(True, "atras")
                else:
                    self._set_motor_ui_state(True, "adelante")
            if dt < self._token_debounce_s:
                self._dbg(
                    "SENSOR",
                    f"TOKEN recibido con dt={dt:.3f}s (< debounce PC {self._token_debounce_s:.3f}s), "
                    "pero no se descarta (MCU autoritativo).",
                )
            with self._tolva_host._tolvas_lock:
                if hopper_id in self._tolva_host._tolvas_trabadas:
                    self._tolva_host._tolvas_trabadas.discard(hopper_id)
            # registro.json legacy: sin escrituras (StateRepository es canónico)
            self._dbg(
                "SENSOR",
                f"TOKEN tolva={hopper_id} mcu_remaining={mcu_remaining_raw} "
                f"pc_before={pc_before} pc_restantes={self._machine_state.get_fichas_restantes()} "
                f"counted={1 if token_counted else 0} delta={counted_delta}",
            )
            print(
                f"[ARDUINO] TOKEN tolva {hopper_id} | restantes={self._machine_state.get_fichas_restantes()} "
                f"(counted={1 if token_counted else 0} delta={counted_delta})"
            )
            self._machine_state.persist_now("token")
            self._send_sale_report_if_done()
            self._notify_gui()
            return
        if etype == "RUN_DONE":
            mcu_rem = max(0, int(evt.get("remaining", 0) or 0))
            pc = int(self._machine_state.get_fichas_restantes())
            self._dbg("MOTOR", f"RUN_DONE mcu={mcu_rem} pc={pc}")
            if pc > 0:
                print(
                    f"[ARDUINO] RUN_DONE ignorado: PC={pc} pendientes, MCU={mcu_rem}; "
                    "re-sincronizando desde PC"
                )
                self._reconcile_with_mcu(mcu_rem, source="RUN_DONE")
                return
            self._machine_state.set_fichas_restantes(0, immediate=False)
            self._machine_state.clear_pending_lots()
            self._reset_offline_motor_cycle()
            self._set_motor_ui_state(False, "detenido")
            self._last_sent_target = 0
            self._last_mcu_remaining = 0
            self._dispense_armed = False
            self._machine_state.persist_now("run_done")
            self._send_sale_report_if_done()
            return
        if etype == "JAM":
            self._destrabe_test_en_curso = False
            self._dbg("MOTOR", f"JAM tolva={hopper_id} msg={evt.get('message')} remaining={evt.get('remaining')}")
            self._tolva_host.bloqueo_emergencia = True
            self._dispense_armed = False
            self._reset_offline_motor_cycle()
            self._set_motor_ui_state(False, "detenido")
            with self._tolva_host._tolvas_lock:
                self._tolva_host._tolvas_trabadas.add(hopper_id)
            fichas = int(evt.get("remaining", self._machine_state.get_fichas_restantes()))
            print(f"[ARDUINO] JAM tolva {hopper_id} | pendientes={fichas}")
            if self._on_motor_alert:
                try:
                    self._on_motor_alert(fichas)
                except Exception as exc:
                    print(f"[SERIAL BRIDGE] alerta GUI: {exc}")
            return
        if etype == "UNJAM_DONE":
            self._dbg("MOTOR", f"UNJAM_DONE tolva={hopper_id}")
            print(f"[ARDUINO] UNJAM_DONE tolva {hopper_id}")
            # Si destrabó, liberar bloqueo para permitir nuevo SET_TARGET.
            self._tolva_host.bloqueo_emergencia = False
            if not self._machine_state.get_motor_activo():
                self._set_motor_ui_state(False, "detenido")
            return
        if etype == "READY":
            self._dbg("BRIDGE", "Arduino READY (config aplicada)")
            print("[ARDUINO] READY")
            return
        if etype == "HELLO_ACK":
            return
        if etype == "ERR":
            msg = str(evt.get("message", evt))
            print(f"[ARDUINO ERR] {msg}")
            if msg == "json_parse" and self._tolva_host.destrabe_pendiente():
                print("[ARDUINO] Destrabe pendiente: comando no llegó bien al MCU; se reintentará")
            return
        if etype == "PONG":
            return

    def _notify_gui(self) -> None:
        if self._on_state_changed:
            try:
                self._on_state_changed()
            except Exception as exc:
                print(f"[SERIAL BRIDGE] GUI callback: {exc}")


_bridge_instance: Optional[SerialBridge] = None


def get_bridge() -> Optional[SerialBridge]:
    return _bridge_instance


def set_bridge(bridge: Optional[SerialBridge]) -> None:
    global _bridge_instance
    _bridge_instance = bridge


def bridge_is_ready() -> bool:
    return _bridge_instance is not None and _bridge_instance.is_ready()


Esp32Bridge = SerialBridge
