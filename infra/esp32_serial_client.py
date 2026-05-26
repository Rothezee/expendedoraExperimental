"""
Cliente serial USB para ESP32 (pyserial).
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional

from infra.esp32_protocol import (
    cmd_config,
    cmd_config_hoppers,
    cmd_hello,
    cmd_ping,
    cmd_select_hopper,
    cmd_set_target,
    cmd_simulate,
    cmd_stop,
    cmd_unjam,
    dumps_frame,
    parse_line,
)
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None  # type: ignore
    list_ports = None  # type: ignore

# VID/PID USB serial (Arduino, adaptadores USB, ESP32 legacy)
_KNOWN_USB_IDS = {
    (0x2341, 0x0043),  # Arduino Uno R3
    (0x2341, 0x0001),  # Arduino Uno
    (0x2341, 0x0010),  # Arduino Mega 2560
    (0x2341, 0x0042),  # Arduino Mega 2560 R3
    (0x2A03, 0x0043),  # Arduino SA Uno
    (0x2A03, 0x0042),  # Arduino SA Mega
    (0x10C4, 0xEA60),
    (0x1A86, 0x7523),
    (0x1A86, 0x55D4),
    (0x0403, 0x6001),
    (0x303A, 0x1001),
    (0x303A, 0x0002),
}


def _serial_port_candidates() -> List[str]:
    """Puertos USB probables (excluye COM legacy sin VID, ej. COM1)."""
    if list_ports is None:
        return []
    priority: List[str] = []
    secondary: List[str] = []
    for info in list_ports.comports():
        device = str(info.device)
        vid = getattr(info, "vid", None)
        pid = getattr(info, "pid", None)
        if vid is None or pid is None:
            continue
        desc = f"{info.description or ''} {info.manufacturer or ''}".lower()
        usb_id = (int(vid), int(pid))
        if (
            "arduino" in desc
            or "mega" in desc
            or "uno" in desc
            or usb_id in _KNOWN_USB_IDS
        ):
            priority.append(device)
        elif "ch340" in desc or "cp210" in desc or "usb serial" in desc or "esp32" in desc:
            secondary.append(device)
        else:
            secondary.append(device)
    seen = set()
    ordered: List[str] = []
    for port in priority + secondary:
        if port not in seen:
            seen.add(port)
            ordered.append(port)
    return ordered


def _esp32_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    hardware = config.get("hardware", {})
    if not isinstance(hardware, dict):
        hardware = {}
    esp = hardware.get("esp32", {})
    if not isinstance(esp, dict):
        esp = {}
    return {
        "port": str(esp.get("port", "")).strip(),
        "baud": int(esp.get("baud", 115200)),
        "auto_detect": bool(esp.get("auto_detect", True)),
        "connect_timeout_s": float(esp.get("connect_timeout_s", 3.0)),
        "command_timeout_ms": int(esp.get("command_timeout_ms", 500)),
        "debug_motor_sensor": bool(esp.get("debug_motor_sensor", False)),
    }


def _write_frame(ser: Any, payload: Dict[str, Any]) -> None:
    ser.write(dumps_frame(payload).encode("utf-8"))
    ser.flush()


def autodetect_port(probe_timeout_s: float = 0.8, *, verbose: bool = False) -> Optional[str]:
    if serial is None or list_ports is None:
        if verbose:
            print("[ESP32] pyserial no disponible para autodetect")
        return None
    ordered = _serial_port_candidates()
    if not ordered:
        if verbose:
            print("[ESP32] Autodetect: no hay puertos USB serial (¿Arduino conectado?)")
        return None
    permission_denied: List[str] = []
    for port in ordered:
        ser = None
        try:
            ser = serial.Serial(port, 115200, timeout=0.05)
            time.sleep(0.25)
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
            _write_frame(ser, cmd_hello())
            deadline = time.time() + probe_timeout_s
            while time.time() < deadline:
                line = ser.readline()
                if not line:
                    continue
                try:
                    text = line.decode("utf-8", errors="replace")
                except Exception:
                    continue
                frame = parse_line(text)
                if frame and str(frame.get("type", "")).upper() in ("READY", "HELLO_ACK", "PONG"):
                    if verbose:
                        print(f"[ESP32] Autodetect: OK en {port}")
                    ser.close()
                    return port
            if verbose:
                print(f"[ESP32] Autodetect: sin HELLO_ACK en {port} ({probe_timeout_s}s)")
            ser.close()
        except PermissionError:
            permission_denied.append(port)
            if verbose:
                print(
                    f"[ESP32] Autodetect: {port} ocupado (cerrá Monitor serie / otra app usando el COM)"
                )
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
        except Exception as exc:
            err = str(exc).lower()
            if "acceso denegado" in err or "permissionerror" in err or "access is denied" in err:
                permission_denied.append(port)
                if verbose:
                    print(
                        f"[ESP32] Autodetect: {port} ocupado (cerrá Monitor serie / otra app usando el COM)"
                    )
            elif verbose:
                print(f"[ESP32] Autodetect: {port} falló ({type(exc).__name__}: {exc})")
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
    if permission_denied and verbose:
        print(
            f"[ESP32] Puertos bloqueados: {permission_denied}. "
            "Cerrá Arduino IDE Monitor serie antes de main.py."
        )
    return None


class Esp32SerialBackend:
    name = "esp32_serial"

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._settings = _esp32_settings(config)
        self._serial: Any = None
        self._reader_thread: Optional[threading.Thread] = None
        self._reader_stop = threading.Event()
        self._event_queue: queue.Queue = queue.Queue()
        self._write_lock = threading.Lock()
        self._connected = False
        self._rx_buffer = ""

    def connect(self) -> bool:
        if serial is None:
            print("[ESP32] pyserial no instalado. pip install pyserial")
            return False
        port = self._settings["port"]
        if self._settings["auto_detect"] and not port:
            port = autodetect_port(
                self._settings["connect_timeout_s"],
                verbose=True,
            ) or ""
        if not port:
            available = _serial_port_candidates()
            if not available and list_ports is not None:
                available = [str(p.device) for p in list_ports.comports()]
            print(
                "[ESP32] No se encontró puerto serial "
                f"(configura hardware.esp32.port, ej. COM4 para Mega). "
                f"USB detectados: {available or 'ninguno'}"
            )
            return False
        try:
            self._serial = serial.Serial(
                port,
                self._settings["baud"],
                timeout=0.05,
                write_timeout=1.0,
            )
            time.sleep(0.2)
            try:
                self._serial.reset_input_buffer()
            except Exception:
                pass
            self._reader_stop.clear()
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            self._send_raw(cmd_hello())
            if not self._wait_for_event(("READY", "HELLO_ACK"), self._settings["connect_timeout_s"]):
                print(f"[ESP32] Sin respuesta READY en {port}")
                self.disconnect()
                return False
            self._connected = True
            print(f"[ESP32] Conectado en {port} @ {self._settings['baud']}")
            return True
        except Exception as exc:
            err = str(exc).lower()
            if "acceso denegado" in err or "permissionerror" in err or "access is denied" in err:
                print(
                    f"[ESP32] {port} ocupado (Acceso denegado). "
                    "Cerrá Monitor serie de Arduino IDE y cualquier otra app que use ese COM."
                )
            else:
                print(f"[ESP32] Error conectando {port}: {exc}")
            self.disconnect()
            return False

    def disconnect(self) -> None:
        self._connected = False
        self._reader_stop.set()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        self._reader_thread = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None

    def is_connected(self) -> bool:
        return self._connected and self._serial is not None

    def configure_hopper(self, hopper: Dict[str, Any], destrabe: Optional[Dict[str, Any]] = None) -> bool:
        ok = self._send_raw(
            cmd_config(hopper, destrabe, debug=self._settings.get("debug_motor_sensor", False))
        )
        if ok:
            return self._wait_for_event(("READY",), 2.0)
        return False

    def configure_hoppers(self, hoppers: List[Dict[str, Any]], destrabe: Optional[Dict[str, Any]] = None) -> bool:
        ok = self._send_raw(
            cmd_config_hoppers(hoppers, destrabe, debug=self._settings.get("debug_motor_sensor", False))
        )
        if ok:
            return self._wait_for_event(("READY",), 2.0)
        return False

    def set_target(self, remaining: int) -> bool:
        return self._send_raw(cmd_set_target(remaining))

    def select_hopper(self, hopper_id: int) -> bool:
        return self._send_raw(cmd_select_hopper(hopper_id))

    def unjam(self, hopper_id: int, retroceso_s: float) -> bool:
        return self._send_raw(cmd_unjam(hopper_id, retroceso_s))

    def stop(self) -> bool:
        return self._send_raw(cmd_stop())

    def ping(self) -> bool:
        return self._send_raw(cmd_ping())

    def simulate_pulse(self) -> bool:
        return self._send_raw(cmd_simulate())

    def poll_events(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _send_raw(self, payload: Dict[str, Any]) -> bool:
        if self._serial is None:
            return False
        line = dumps_frame(payload)
        settings = getattr(self, "_settings", None) or {}
        if settings.get("debug_motor_sensor"):
            print(f"[DBG PC→ESP32] TX {line.strip()}")
        try:
            with self._write_lock:
                self._serial.write(line.encode("utf-8"))
                self._serial.flush()
            return True
        except Exception as exc:
            print(f"[ESP32] Error enviando {payload.get('type')}: {exc}")
            self._connected = False
            return False

    def _reader_loop(self) -> None:
        while not self._reader_stop.is_set():
            ser = self._serial
            if ser is None:
                break
            try:
                chunk = ser.read(256)
                if not chunk:
                    continue
                self._rx_buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in self._rx_buffer:
                    line, self._rx_buffer = self._rx_buffer.split("\n", 1)
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped.startswith("[DBG"):
                        if self._settings.get("debug_motor_sensor"):
                            print(f"[DBG ESP32→PC] {stripped}")
                        continue
                    frame = parse_line(line)
                    if frame:
                        if self._settings.get("debug_motor_sensor"):
                            evt_type = str(frame.get("type", ""))
                            if evt_type in (
                                "MOTOR_ON",
                                "MOTOR_OFF",
                                "TOKEN",
                                "SYNC",
                                "RUN_DONE",
                                "JAM",
                                "READY",
                                "ERR",
                            ):
                                print(f"[DBG ESP32→PC] EVT {stripped}")
                        self._event_queue.put(frame)
            except Exception as exc:
                if not self._reader_stop.is_set():
                    print(f"[ESP32] Reader error: {exc}")
                break
            time.sleep(0.001)

    def _wait_for_event(self, types: tuple, timeout_s: float) -> bool:
        deadline = time.time() + timeout_s
        wanted = {t.upper() for t in types}
        while time.time() < deadline:
            for evt in self.poll_events():
                if str(evt.get("type", "")).upper() in wanted:
                    return True
            time.sleep(0.02)
        return False
