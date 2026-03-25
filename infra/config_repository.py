import json
import os
from typing import Any, Dict


DEFAULT_API_BASE_URLS = ["http://127.0.0.1", "https://maquinasbonus.com"]
DEFAULT_API_ENDPOINT = "AdministrationPanel/src/devices/api_receptor.php"
DEFAULT_API_TIMEOUT_S = 5
DEFAULT_DNI_ADMIN = "00000000"
DEFAULT_HEARTBEAT_INTERVAL_S = 600
DEFAULT_MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "sistemadeadministracion",
}
DEFAULT_UPDATER_CONFIG = {
    "enabled": False,
    "remote": "origin",
    "branch": "main",
    "check_interval_s": 300,
    "run_pip_install": False,
    "requirements_file": "requirements.txt",
    "restart_command_linux": "",
    "restart_command_windows": "",
    "preserve_files": ["config.json", "registro.json", "buffer_state.json"],
}


class ConfigRepository:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path

    @staticmethod
    def _safe_int(value: Any, default: int, minimum: int | None = None) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = default
        if minimum is not None and parsed < minimum:
            return minimum
        return parsed

    def normalize(self, config: Dict[str, Any] | None) -> Dict[str, Any]:
        if not isinstance(config, dict):
            config = {}

        legacy_device_id = str(config.get("device_id", "") or "").strip()

        api = config.get("api", {})
        if not isinstance(api, dict):
            api = {}
        base_urls = api.get("base_urls", DEFAULT_API_BASE_URLS)
        if isinstance(base_urls, str):
            base_urls = [base_urls]
        if not isinstance(base_urls, list) or not base_urls:
            base_urls = list(DEFAULT_API_BASE_URLS)
        base_urls = [str(url).strip() for url in base_urls if str(url).strip()]
        if not base_urls:
            base_urls = list(DEFAULT_API_BASE_URLS)
        endpoint = str(api.get("endpoint_receptor", DEFAULT_API_ENDPOINT) or "").strip().lstrip("/")
        timeout_s = self._safe_int(api.get("timeout_s", DEFAULT_API_TIMEOUT_S), DEFAULT_API_TIMEOUT_S, minimum=1)

        admin = config.get("admin", {})
        if not isinstance(admin, dict):
            admin = {}
        dni_admin = str(admin.get("dni_admin", config.get("dni_admin", DEFAULT_DNI_ADMIN)) or "").strip() or DEFAULT_DNI_ADMIN

        maquina = config.get("maquina", {})
        if not isinstance(maquina, dict):
            maquina = {}
        codigo_hardware = str(maquina.get("codigo_hardware", config.get("codigo_hardware", legacy_device_id)) or "").strip()

        heartbeat = config.get("heartbeat", {})
        if not isinstance(heartbeat, dict):
            heartbeat = {}
        intervalo_s = self._safe_int(
            heartbeat.get("intervalo_s", DEFAULT_HEARTBEAT_INTERVAL_S),
            DEFAULT_HEARTBEAT_INTERVAL_S,
            minimum=10,
        )

        mysql = config.get("mysql", {})
        if not isinstance(mysql, dict):
            mysql = {}
        mysql_cfg = {
            "host": str(mysql.get("host", DEFAULT_MYSQL_CONFIG["host"])),
            "port": self._safe_int(mysql.get("port", DEFAULT_MYSQL_CONFIG["port"]), DEFAULT_MYSQL_CONFIG["port"], minimum=1),
            "user": str(mysql.get("user", DEFAULT_MYSQL_CONFIG["user"])),
            "password": str(mysql.get("password", DEFAULT_MYSQL_CONFIG["password"])),
            "database": str(mysql.get("database", DEFAULT_MYSQL_CONFIG["database"])),
        }

        updater = config.get("updater", {})
        if not isinstance(updater, dict):
            updater = {}
        preserve_files = updater.get("preserve_files", DEFAULT_UPDATER_CONFIG["preserve_files"])
        if not isinstance(preserve_files, list):
            preserve_files = list(DEFAULT_UPDATER_CONFIG["preserve_files"])
        preserve_files = [str(path).strip() for path in preserve_files if str(path).strip()]
        if not preserve_files:
            preserve_files = list(DEFAULT_UPDATER_CONFIG["preserve_files"])
        updater_cfg = {
            "enabled": bool(updater.get("enabled", DEFAULT_UPDATER_CONFIG["enabled"])),
            "remote": str(updater.get("remote", DEFAULT_UPDATER_CONFIG["remote"])),
            "branch": str(updater.get("branch", DEFAULT_UPDATER_CONFIG["branch"])),
            "check_interval_s": self._safe_int(
                updater.get("check_interval_s", DEFAULT_UPDATER_CONFIG["check_interval_s"]),
                DEFAULT_UPDATER_CONFIG["check_interval_s"],
                minimum=30,
            ),
            "run_pip_install": bool(updater.get("run_pip_install", DEFAULT_UPDATER_CONFIG["run_pip_install"])),
            "requirements_file": str(updater.get("requirements_file", DEFAULT_UPDATER_CONFIG["requirements_file"])),
            "restart_command_linux": str(updater.get("restart_command_linux", DEFAULT_UPDATER_CONFIG["restart_command_linux"])),
            "restart_command_windows": str(updater.get("restart_command_windows", DEFAULT_UPDATER_CONFIG["restart_command_windows"])),
            "preserve_files": preserve_files,
        }

        merged = dict(config)
        merged["api"] = {
            "base_urls": base_urls,
            "endpoint_receptor": endpoint,
            "timeout_s": timeout_s,
        }
        merged["admin"] = {"dni_admin": dni_admin}
        merged["maquina"] = {"codigo_hardware": codigo_hardware, "tipo_maquina": 1}
        merged["heartbeat"] = {"intervalo_s": intervalo_s}
        merged["mysql"] = mysql_cfg
        merged["updater"] = updater_cfg
        merged["device_id"] = codigo_hardware
        return merged

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            return self.normalize(data)
        return self.normalize({"promociones": {}, "valor_ficha": 1.0})

    def save(self, config: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self.normalize(config)
        with open(self.config_path, "w", encoding="utf-8") as file_obj:
            json.dump(normalized, file_obj, indent=4)
        return normalized

