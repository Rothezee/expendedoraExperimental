import platform
import socket
import subprocess
import threading
from datetime import datetime
from typing import Callable

import requests

from infra.config_repository import ConfigRepository


class NetworkManagerService:
    def __init__(self, config_repository: ConfigRepository):
        self.config_repository = config_repository
        self._status_lock = threading.Lock()
        self._status = {
            "enabled": True,
            "level": "UNKNOWN",
            "message": "Inicializando",
            "active_connection": "",
            "active_device": "",
            "internet_ok": False,
            "backend_ok": False,
            "signal_percent": None,
            "reconnect_attempts": 0,
            "last_reconnect_at": "",
            "last_change_at": "",
            "last_error": "",
        }
        self._callback: Callable[[dict], None] | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_level = "UNKNOWN"

    def start(self, callback: Callable[[dict], None] | None = None):
        if self._thread and self._thread.is_alive():
            return
        self._callback = callback
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def get_status(self) -> dict:
        with self._status_lock:
            return dict(self._status)

    def _load_network_cfg(self) -> dict:
        config = self.config_repository.load()
        raw = config.get("network_manager", {})
        if not isinstance(raw, dict):
            raw = {}
        enabled = bool(raw.get("enabled", True))
        check_interval_s = self._safe_int(raw.get("check_interval_s", 8), default=8, minimum=2)
        reconnect_after_failures = self._safe_int(raw.get("reconnect_after_failures", 3), default=3, minimum=1)
        backend_timeout_s = self._safe_float(raw.get("backend_timeout_s", 3.0), default=3.0, minimum=0.5)
        internet_host = str(raw.get("internet_host", "8.8.8.8") or "").strip() or "8.8.8.8"
        backend_url = str(raw.get("backend_url", "") or "").strip()
        preferred_interface = str(raw.get("preferred_interface", "") or "").strip()
        wifi_ssid = str(raw.get("wifi_ssid", "") or "").strip()
        wifi_password = str(raw.get("wifi_password", "") or "")
        return {
            "enabled": enabled,
            "check_interval_s": check_interval_s,
            "reconnect_after_failures": reconnect_after_failures,
            "backend_timeout_s": backend_timeout_s,
            "internet_host": internet_host,
            "backend_url": backend_url,
            "preferred_interface": preferred_interface,
            "wifi_ssid": wifi_ssid,
            "wifi_password": wifi_password,
        }

    @staticmethod
    def _safe_int(value, default: int, minimum: int = 0) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = default
        return max(parsed, minimum)

    @staticmethod
    def _safe_float(value, default: float, minimum: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(parsed, minimum)

    def _run_loop(self):
        consecutive_failures = 0
        while not self._stop_event.is_set():
            cfg = self._load_network_cfg()
            if not cfg["enabled"]:
                self._set_status(
                    level="DISABLED",
                    message="Gestor de red deshabilitado",
                    enabled=False,
                )
                self._stop_event.wait(cfg["check_interval_s"])
                continue

            supported = platform.system().lower() == "linux"
            snapshot = self._collect_snapshot(cfg, supported=supported)
            internet_ok = bool(snapshot.get("internet_ok"))
            backend_ok = bool(snapshot.get("backend_ok"))
            active_connection = str(snapshot.get("active_connection") or "")

            if active_connection and (internet_ok or backend_ok):
                level = "ONLINE"
                message = "Conectado"
                consecutive_failures = 0
            elif active_connection:
                level = "DEGRADED"
                message = "Conectado sin salida estable"
                consecutive_failures += 1
            else:
                level = "OFFLINE"
                message = "Sin conexión activa"
                consecutive_failures += 1

            self._set_status(
                enabled=True,
                level=level,
                message=message,
                active_connection=active_connection,
                active_device=snapshot.get("active_device", ""),
                internet_ok=internet_ok,
                backend_ok=backend_ok,
                signal_percent=snapshot.get("signal_percent"),
                last_error=snapshot.get("last_error", ""),
            )

            should_reconnect = supported and consecutive_failures >= cfg["reconnect_after_failures"]
            if should_reconnect:
                self._attempt_reconnect(cfg, snapshot)
                consecutive_failures = 0

            self._stop_event.wait(cfg["check_interval_s"])

    def _set_status(self, **updates):
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        callback_payload = None
        with self._status_lock:
            current = dict(self._status)
            current.update(updates)
            if current.get("level") != self._last_level:
                current["last_change_at"] = now_iso
                self._last_level = str(current.get("level"))
            self._status = current
            callback_payload = dict(self._status)
        if self._callback:
            try:
                self._callback(callback_payload)
            except Exception as exc:
                print(f"[NET] callback error: {exc}")

    def _collect_snapshot(self, cfg: dict, supported: bool) -> dict:
        snapshot = {
            "active_connection": "",
            "active_device": "",
            "signal_percent": None,
            "internet_ok": False,
            "backend_ok": False,
            "last_error": "",
        }
        if not supported:
            snapshot["last_error"] = "NetworkManager no soportado en este sistema."
            return snapshot

        active = self._nmcli_active_connection(preferred_interface=cfg.get("preferred_interface", ""))
        snapshot.update(active)
        snapshot["internet_ok"] = self._check_internet(cfg["internet_host"])
        snapshot["backend_ok"] = self._check_backend(cfg["backend_url"], cfg["backend_timeout_s"])
        if not snapshot["active_connection"]:
            snapshot["last_error"] = "No hay conexión activa en NetworkManager."
        return snapshot

    def _nmcli_active_connection(self, preferred_interface: str = "") -> dict:
        result = {
            "active_connection": "",
            "active_device": "",
            "signal_percent": None,
        }
        try:
            output = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "connection", "show", "--active"],
                check=False,
                capture_output=True,
                text=True,
                timeout=4,
            )
            lines = [line.strip() for line in output.stdout.splitlines() if line.strip()]
            if not lines:
                return result
            selected = None
            if preferred_interface:
                for line in lines:
                    parts = line.split(":")
                    if len(parts) >= 2 and parts[1] == preferred_interface:
                        selected = line
                        break
            if not selected:
                selected = lines[0]
            parts = selected.split(":")
            if len(parts) >= 2:
                result["active_connection"] = parts[0]
                result["active_device"] = parts[1]
            signal = self._nmcli_wifi_signal(result["active_device"])
            result["signal_percent"] = signal
        except Exception as exc:
            print(f"[NET] nmcli active error: {exc}")
        return result

    @staticmethod
    def _nmcli_wifi_signal(device: str) -> int | None:
        if not device:
            return None
        try:
            output = subprocess.run(
                ["nmcli", "-t", "-f", "IN-USE,SIGNAL", "device", "wifi", "list", "ifname", device],
                check=False,
                capture_output=True,
                text=True,
                timeout=4,
            )
            for line in output.stdout.splitlines():
                row = line.strip()
                if row.startswith("*:"):
                    parts = row.split(":")
                    if len(parts) == 2:
                        return int(float(parts[1]))
        except Exception:
            return None
        return None

    @staticmethod
    def _check_internet(host: str) -> bool:
        try:
            socket.create_connection((host, 53), timeout=2).close()
            return True
        except Exception:
            return False

    @staticmethod
    def _check_backend(url: str, timeout_s: float) -> bool:
        if not url:
            return False
        try:
            response = requests.get(url, timeout=timeout_s)
            return response.status_code < 500
        except Exception:
            return False

    def _attempt_reconnect(self, cfg: dict, snapshot: dict):
        preferred_interface = cfg.get("preferred_interface", "")
        active_device = str(snapshot.get("active_device") or "")
        device = preferred_interface or active_device
        try:
            subprocess.run(["nmcli", "networking", "on"], check=False, capture_output=True, text=True, timeout=4)
            subprocess.run(["nmcli", "radio", "wifi", "on"], check=False, capture_output=True, text=True, timeout=4)
            ssid = str(cfg.get("wifi_ssid") or "").strip()
            if ssid:
                ok, error_msg = self._connect_wifi(ssid, str(cfg.get("wifi_password") or ""), device)
                if not ok:
                    self._set_status(last_error=error_msg)
            elif device:
                subprocess.run(
                    ["nmcli", "device", "connect", device],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=6,
                )
            else:
                subprocess.run(
                    ["nmcli", "connection", "up", "id", str(snapshot.get("active_connection") or "")],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=6,
                )
            status = self.get_status()
            attempts = int(status.get("reconnect_attempts", 0)) + 1
            self._set_status(
                reconnect_attempts=attempts,
                last_reconnect_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            print(f"[NET] Intento de reconexión #{attempts}")
        except Exception as exc:
            self._set_status(last_error=f"Reconexión fallida: {exc}")
            print(f"[NET] reconnection error: {exc}")

    def connect_configured_network(self) -> tuple[bool, str]:
        cfg = self._load_network_cfg()
        if platform.system().lower() != "linux":
            return False, "Conexión Wi-Fi manual disponible solo en Linux con nmcli."
        ssid = str(cfg.get("wifi_ssid") or "").strip()
        if not ssid:
            return False, "No se configuró ningún SSID."
        preferred_interface = str(cfg.get("preferred_interface") or "").strip()
        return self._connect_wifi(ssid, str(cfg.get("wifi_password") or ""), preferred_interface)

    @staticmethod
    def _connect_wifi(ssid: str, password: str, interface: str = "") -> tuple[bool, str]:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            cmd.extend(["password", password])
        if interface:
            cmd.extend(["ifname", interface])
        try:
            output = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if output.returncode == 0:
                return True, "Conexión Wi-Fi iniciada."

            details = (output.stderr or output.stdout or "").strip()
            fallback_cmd = ["nmcli", "connection", "up", ssid]
            if interface:
                fallback_cmd.extend(["ifname", interface])
            fallback = subprocess.run(
                fallback_cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if fallback.returncode == 0:
                return True, "Perfil Wi-Fi existente activado."
            fallback_details = (fallback.stderr or fallback.stdout or "").strip()
            message = fallback_details or details or "No se pudo conectar con nmcli."
            return False, message
        except Exception as exc:
            return False, f"Error ejecutando nmcli: {exc}"
