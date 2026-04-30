import json
import os
from typing import Any, Dict


DEFAULT_API_BASE_URLS = ["http://127.0.0.1", "https://app.maquinasbonus.com"]
DEFAULT_API_ENDPOINT = "AdministrationPanel/src/devices/api_receptor.php"
DEFAULT_API_ENDPOINT_LOCAL = "AdministrationPanel/src/devices/api_receptor.php"
DEFAULT_API_ENDPOINT_CLOUD = "src/devices/api_receptor.php"
DEFAULT_API_ENDPOINT_CLOUD_FALLBACK = ""
DEFAULT_API_TIMEOUT_S = 5
DEFAULT_API_HEADERS: Dict[str, str] = {}
DEFAULT_DNI_ADMIN = "00000000"
DEFAULT_HEARTBEAT_INTERVAL_S = 600
DEFAULT_MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "sistemadeadministracion",
}
DEFAULT_HOPPERS = [
    {"id": 1, "nombre": "Tolva 1", "motor_pin": 3, "motor_pin_rev": None, "motor_active_low": True, "sensor_pin": 4, "sensor_bouncetime_ms": 8},
    {"id": 2, "nombre": "Tolva 2", "motor_pin": 3, "motor_pin_rev": None, "motor_active_low": True, "sensor_pin": 4, "sensor_bouncetime_ms": 8},
    {"id": 3, "nombre": "Tolva 3", "motor_pin": 3, "motor_pin_rev": None, "motor_active_low": True, "sensor_pin": 4, "sensor_bouncetime_ms": 8},
]
DEFAULT_HOPPER_CALIBRATION = {
    "pulso_min_s": 0.05,
    "pulso_max_s": 0.5,
    "timeout_motor_s": 2.0,
}

DEFAULT_DESTRABE_CONFIG = {
    "enabled": True,
    "auto_on_timeout": True,
    "retroceso_s": 1.5,
    "max_intentos": 1,
    "cooldown_s": 2.0,
}
DEFAULT_SENSOR_INTERRUPTS_CONFIG = {
    "bouncetime_ms": 8,
}
DEFAULT_PROMO_HOTKEYS = {
    "Promo 1": ["<slash>", "<KP_Divide>"],
    "Promo 2": ["<asterisk>", "<KP_Multiply>", "x", "X"],
    "Promo 3": ["<minus>", "<KP_Subtract>"],
}
DEFAULT_MYSQL_MULTI_CONFIG = {
    "active": "local",
    "fallback_to_secondary": True,
    "local": dict(DEFAULT_MYSQL_CONFIG),
    "production": dict(DEFAULT_MYSQL_CONFIG),
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
DEFAULT_NETWORK_MANAGER_CONFIG = {
    "enabled": True,
    "check_interval_s": 8,
    "reconnect_after_failures": 3,
    "backend_timeout_s": 3.0,
    "internet_host": "8.8.8.8",
    "backend_url": "https://maquinasbonus.com/",
    "preferred_interface": "",
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

    @staticmethod
    def _safe_float(value: Any, default: float, minimum: float | None = None) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        if minimum is not None and parsed < minimum:
            return minimum
        return parsed

    @staticmethod
    def _mysql_scalar_str(value: Any, default: str) -> str:
        """Evita str(None) == 'None' cuando JSON trae null en user/password/host/database."""
        if value is None:
            return default
        return str(value)

    @staticmethod
    def mysql_connection_params(profile: Dict[str, Any] | None) -> Dict[str, Any]:
        """
        Perfil normalizado (local/production) o parcial → kwargs para mysql.connector.connect.
        """
        if not isinstance(profile, dict):
            profile = {}
        d = DEFAULT_MYSQL_CONFIG
        return {
            "host": str(ConfigRepository._mysql_scalar_str(profile.get("host"), d["host"]) or d["host"]).strip()
            or d["host"],
            "port": ConfigRepository._safe_int(profile.get("port", d["port"]), d["port"], minimum=1),
            "user": ConfigRepository._mysql_scalar_str(profile.get("user"), d["user"]),
            "password": ConfigRepository._mysql_scalar_str(profile.get("password"), d["password"]),
            "database": ConfigRepository._mysql_scalar_str(profile.get("database"), d["database"]),
            "connection_timeout": 12,
        }

    @staticmethod
    def _is_mysql_host_local(host: str) -> bool:
        h = str(host or "").strip().lower()
        return h in ("localhost", "127.0.0.1", "::1")

    @staticmethod
    def iter_mysql_targets_from_section(
        mysql_cfg: Dict[str, Any] | None,
        *,
        prefer_local_first: bool = False,
        production_only: bool = False,
    ) -> list[Dict[str, Any]]:
        """
        Orden de intentos de conexión según active/fallback.
        prefer_local_first: como la UI de reportes (todos los hosts locales antes que remotos).
        production_only: sólo perfil production (registro remoto de cajero).
        """
        if not isinstance(mysql_cfg, dict):
            mysql_cfg = {}
        legacy_keys = ("host", "port", "user", "password", "database")
        if any(k in mysql_cfg for k in legacy_keys):
            legacy_profile = {
                "host": mysql_cfg.get("host", DEFAULT_MYSQL_CONFIG["host"]),
                "port": mysql_cfg.get("port", DEFAULT_MYSQL_CONFIG["port"]),
                "user": mysql_cfg.get("user", DEFAULT_MYSQL_CONFIG["user"]),
                "password": mysql_cfg.get("password", DEFAULT_MYSQL_CONFIG["password"]),
                "database": mysql_cfg.get("database", DEFAULT_MYSQL_CONFIG["database"]),
            }
            return [ConfigRepository.mysql_connection_params(legacy_profile)]

        local_raw = mysql_cfg.get("local", {})
        prod_raw = mysql_cfg.get("production", {})
        if not isinstance(local_raw, dict):
            local_raw = {}
        if not isinstance(prod_raw, dict):
            prod_raw = {}
        local_params = ConfigRepository.mysql_connection_params(local_raw)
        prod_params = ConfigRepository.mysql_connection_params(prod_raw)

        if production_only:
            return [prod_params]

        active = str(mysql_cfg.get("active", DEFAULT_MYSQL_MULTI_CONFIG["active"]) or "").lower()
        if active not in ("local", "production"):
            active = str(DEFAULT_MYSQL_MULTI_CONFIG["active"]).lower()
        fallback = bool(mysql_cfg.get("fallback_to_secondary", DEFAULT_MYSQL_MULTI_CONFIG["fallback_to_secondary"]))

        if active == "production":
            ordered = [prod_params, local_params] if fallback else [prod_params]
        else:
            ordered = [local_params, prod_params] if fallback else [local_params]

        if prefer_local_first:
            ordered = sorted(ordered, key=lambda t: (0 if ConfigRepository._is_mysql_host_local(t.get("host", "")) else 1))
        return ordered

    def iter_mysql_targets(
        self,
        *,
        prefer_local_first: bool = False,
        production_only: bool = False,
    ) -> list[Dict[str, Any]]:
        cfg = self.load()
        mysql_cfg = cfg.get("mysql", {})
        if not isinstance(mysql_cfg, dict):
            mysql_cfg = {}
        return ConfigRepository.iter_mysql_targets_from_section(
            mysql_cfg,
            prefer_local_first=prefer_local_first,
            production_only=production_only,
        )

    def normalize(self, config: Dict[str, Any] | None) -> Dict[str, Any]:
        if not isinstance(config, dict):
            config = {}

        legacy_device_id = str(config.get("device_id", "") or "").strip()

        api = config.get("api", {})
        if not isinstance(api, dict):
            api = {}
        base_urls = api.get("base_urls", DEFAULT_API_BASE_URLS)
        local_base = str(api.get("local_base_url", "") or "").strip()
        prod_base = str(api.get("production_base_url", "") or "").strip()
        if isinstance(base_urls, str):
            base_urls = [base_urls]
        if not isinstance(base_urls, list) or not base_urls:
            base_urls = list(DEFAULT_API_BASE_URLS)
        base_urls = [str(url).strip() for url in base_urls if str(url).strip()]
        if local_base:
            base_urls.insert(0, local_base)
        if prod_base:
            base_urls.append(prod_base)
        # Deduplicar preservando orden
        dedup_base_urls: list[str] = []
        for url in base_urls:
            if url not in dedup_base_urls:
                dedup_base_urls.append(url)
        base_urls = dedup_base_urls
        if not base_urls:
            base_urls = list(DEFAULT_API_BASE_URLS)
        endpoint = str(api.get("endpoint_receptor", DEFAULT_API_ENDPOINT) or "").strip().lstrip("/")
        endpoint_local = str(
            api.get("endpoint_receptor_local", endpoint or DEFAULT_API_ENDPOINT_LOCAL) or ""
        ).strip().lstrip("/")
        endpoint_cloud = str(api.get("endpoint_receptor_cloud", "") or "").strip().lstrip("/")
        if not endpoint_cloud:
            if endpoint.startswith("AdministrationPanel/"):
                endpoint_cloud = endpoint.replace("AdministrationPanel/", "", 1)
            else:
                endpoint_cloud = endpoint or DEFAULT_API_ENDPOINT_CLOUD
        endpoint_cloud_fallback = str(api.get("endpoint_receptor_cloud_fallback", DEFAULT_API_ENDPOINT_CLOUD_FALLBACK) or "").strip().lstrip("/")
        timeout_s = self._safe_int(api.get("timeout_s", DEFAULT_API_TIMEOUT_S), DEFAULT_API_TIMEOUT_S, minimum=1)
        headers_raw = api.get("headers", DEFAULT_API_HEADERS)
        if not isinstance(headers_raw, dict):
            headers_raw = {}
        headers = {}
        for key, value in headers_raw.items():
            key_str = str(key).strip()
            value_str = str(value).strip()
            if key_str and value_str:
                headers[key_str] = value_str

        admin = config.get("admin", {})
        if not isinstance(admin, dict):
            admin = {}
        dni_admin = str(admin.get("dni_admin", config.get("dni_admin", DEFAULT_DNI_ADMIN)) or "").strip() or DEFAULT_DNI_ADMIN

        maquina = config.get("maquina", {})
        if not isinstance(maquina, dict):
            maquina = {}
        codigo_hardware = str(maquina.get("codigo_hardware", config.get("codigo_hardware", legacy_device_id)) or "").strip()
        raw_sensor_interrupts = maquina.get("sensor_interrupts", {})
        if not isinstance(raw_sensor_interrupts, dict):
            raw_sensor_interrupts = {}
        sensor_interrupts_cfg = {
            "bouncetime_ms": self._safe_int(
                raw_sensor_interrupts.get("bouncetime_ms", DEFAULT_SENSOR_INTERRUPTS_CONFIG["bouncetime_ms"]),
                DEFAULT_SENSOR_INTERRUPTS_CONFIG["bouncetime_ms"],
                minimum=0,
            ),
        }
        hoppers = maquina.get("hoppers", DEFAULT_HOPPERS)
        if not isinstance(hoppers, list) or not hoppers:
            hoppers = list(DEFAULT_HOPPERS)
        normalized_hoppers = []
        for idx, hopper in enumerate(hoppers[:3], start=1):
            if not isinstance(hopper, dict):
                hopper = {}
            fallback = DEFAULT_HOPPERS[idx - 1] if idx - 1 < len(DEFAULT_HOPPERS) else DEFAULT_HOPPERS[0]
            raw_calib = hopper.get("calibracion", {})
            if not isinstance(raw_calib, dict):
                raw_calib = {}
            normalized_hoppers.append(
                {
                    "id": self._safe_int(hopper.get("id", idx), idx, minimum=1),
                    "nombre": str(hopper.get("nombre", fallback["nombre"])),
                    "motor_pin": self._safe_int(hopper.get("motor_pin", fallback["motor_pin"]), fallback["motor_pin"], minimum=1),
                    "motor_pin_rev": (
                        self._safe_int(hopper.get("motor_pin_rev"), fallback.get("motor_pin_rev") or 0, minimum=1)
                        if hopper.get("motor_pin_rev") is not None
                        else None
                    ),
                    "motor_active_low": bool(hopper.get("motor_active_low", fallback.get("motor_active_low", True))),
                    "sensor_pin": self._safe_int(hopper.get("sensor_pin", fallback["sensor_pin"]), fallback["sensor_pin"], minimum=1),
                    "sensor_bouncetime_ms": self._safe_int(
                        hopper.get("sensor_bouncetime_ms", sensor_interrupts_cfg["bouncetime_ms"]),
                        sensor_interrupts_cfg["bouncetime_ms"],
                        minimum=0,
                    ),
                    "calibracion": {
                        "pulso_min_s": self._safe_float(
                            raw_calib.get("pulso_min_s", DEFAULT_HOPPER_CALIBRATION["pulso_min_s"]),
                            DEFAULT_HOPPER_CALIBRATION["pulso_min_s"],
                            minimum=0.001,
                        ),
                        "pulso_max_s": self._safe_float(
                            raw_calib.get("pulso_max_s", DEFAULT_HOPPER_CALIBRATION["pulso_max_s"]),
                            DEFAULT_HOPPER_CALIBRATION["pulso_max_s"],
                            minimum=0.001,
                        ),
                        "timeout_motor_s": self._safe_float(
                            raw_calib.get("timeout_motor_s", DEFAULT_HOPPER_CALIBRATION["timeout_motor_s"]),
                            DEFAULT_HOPPER_CALIBRATION["timeout_motor_s"],
                            minimum=0.1,
                        ),
                    },
                }
            )
            # Si quedaron invertidos por carga manual, los corregimos.
            calib = normalized_hoppers[-1]["calibracion"]
            if calib["pulso_max_s"] < calib["pulso_min_s"]:
                calib["pulso_max_s"] = calib["pulso_min_s"]
        while len(normalized_hoppers) < 3:
            fallback = DEFAULT_HOPPERS[len(normalized_hoppers)]
            normalized_hoppers.append(
                {
                    "id": fallback["id"],
                    "nombre": fallback["nombre"],
                    "motor_pin": fallback["motor_pin"],
                    "motor_pin_rev": fallback.get("motor_pin_rev"),
                    "motor_active_low": bool(fallback.get("motor_active_low", True)),
                    "sensor_pin": fallback["sensor_pin"],
                    "sensor_bouncetime_ms": self._safe_int(
                        fallback.get("sensor_bouncetime_ms", sensor_interrupts_cfg["bouncetime_ms"]),
                        sensor_interrupts_cfg["bouncetime_ms"],
                        minimum=0,
                    ),
                    "calibracion": dict(DEFAULT_HOPPER_CALIBRATION),
                }
            )

        atajos = config.get("atajos", {})
        if not isinstance(atajos, dict):
            atajos = {}
        promo_hotkeys = atajos.get("promociones", {})
        if not isinstance(promo_hotkeys, dict):
            promo_hotkeys = {}
        normalized_hotkeys = {}
        for promo_name, default_keys in DEFAULT_PROMO_HOTKEYS.items():
            keys = promo_hotkeys.get(promo_name, default_keys)
            if isinstance(keys, str):
                keys = [keys]
            if not isinstance(keys, list):
                keys = list(default_keys)
            clean_keys = []
            for key in keys:
                key_str = str(key).strip()
                if key_str and key_str not in clean_keys:
                    clean_keys.append(key_str)
            if not clean_keys:
                clean_keys = list(default_keys)
            normalized_hotkeys[promo_name] = clean_keys

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

        # Compatibilidad: formato viejo plano mysql.host/mysql.user/...
        if any(key in mysql for key in ("host", "port", "user", "password", "database")):
            legacy_conn = {
                "host": self._mysql_scalar_str(mysql.get("host"), DEFAULT_MYSQL_CONFIG["host"]),
                "port": self._safe_int(mysql.get("port", DEFAULT_MYSQL_CONFIG["port"]), DEFAULT_MYSQL_CONFIG["port"], minimum=1),
                "user": self._mysql_scalar_str(mysql.get("user"), DEFAULT_MYSQL_CONFIG["user"]),
                "password": self._mysql_scalar_str(mysql.get("password"), DEFAULT_MYSQL_CONFIG["password"]),
                "database": self._mysql_scalar_str(mysql.get("database"), DEFAULT_MYSQL_CONFIG["database"]),
            }
            active_raw = mysql.get("active", DEFAULT_MYSQL_MULTI_CONFIG["active"])
            mysql_cfg = {
                "active": self._mysql_scalar_str(active_raw, DEFAULT_MYSQL_MULTI_CONFIG["active"]).lower(),
                "fallback_to_secondary": bool(mysql.get("fallback_to_secondary", DEFAULT_MYSQL_MULTI_CONFIG["fallback_to_secondary"])),
                "local": dict(legacy_conn),
                "production": dict(legacy_conn),
            }
        else:
            local_cfg_raw = mysql.get("local", {})
            if not isinstance(local_cfg_raw, dict):
                local_cfg_raw = {}
            prod_cfg_raw = mysql.get("production", {})
            if not isinstance(prod_cfg_raw, dict):
                prod_cfg_raw = {}
            active_raw = mysql.get("active", DEFAULT_MYSQL_MULTI_CONFIG["active"])
            mysql_cfg = {
                "active": self._mysql_scalar_str(active_raw, DEFAULT_MYSQL_MULTI_CONFIG["active"]).lower(),
                "fallback_to_secondary": bool(mysql.get("fallback_to_secondary", DEFAULT_MYSQL_MULTI_CONFIG["fallback_to_secondary"])),
                "local": {
                    "host": self._mysql_scalar_str(local_cfg_raw.get("host"), DEFAULT_MYSQL_MULTI_CONFIG["local"]["host"]),
                    "port": self._safe_int(local_cfg_raw.get("port", DEFAULT_MYSQL_MULTI_CONFIG["local"]["port"]), DEFAULT_MYSQL_MULTI_CONFIG["local"]["port"], minimum=1),
                    "user": self._mysql_scalar_str(local_cfg_raw.get("user"), DEFAULT_MYSQL_MULTI_CONFIG["local"]["user"]),
                    "password": self._mysql_scalar_str(local_cfg_raw.get("password"), DEFAULT_MYSQL_MULTI_CONFIG["local"]["password"]),
                    "database": self._mysql_scalar_str(local_cfg_raw.get("database"), DEFAULT_MYSQL_MULTI_CONFIG["local"]["database"]),
                },
                "production": {
                    "host": self._mysql_scalar_str(prod_cfg_raw.get("host"), DEFAULT_MYSQL_MULTI_CONFIG["production"]["host"]),
                    "port": self._safe_int(prod_cfg_raw.get("port", DEFAULT_MYSQL_MULTI_CONFIG["production"]["port"]), DEFAULT_MYSQL_MULTI_CONFIG["production"]["port"], minimum=1),
                    "user": self._mysql_scalar_str(prod_cfg_raw.get("user"), DEFAULT_MYSQL_MULTI_CONFIG["production"]["user"]),
                    "password": self._mysql_scalar_str(prod_cfg_raw.get("password"), DEFAULT_MYSQL_MULTI_CONFIG["production"]["password"]),
                    "database": self._mysql_scalar_str(prod_cfg_raw.get("database"), DEFAULT_MYSQL_MULTI_CONFIG["production"]["database"]),
                },
            }

        if mysql_cfg["active"] not in ("local", "production"):
            mysql_cfg["active"] = DEFAULT_MYSQL_MULTI_CONFIG["active"]

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
        network_manager = config.get("network_manager", {})
        if not isinstance(network_manager, dict):
            network_manager = {}
        network_manager_cfg = {
            "enabled": bool(network_manager.get("enabled", DEFAULT_NETWORK_MANAGER_CONFIG["enabled"])),
            "check_interval_s": self._safe_int(
                network_manager.get("check_interval_s", DEFAULT_NETWORK_MANAGER_CONFIG["check_interval_s"]),
                DEFAULT_NETWORK_MANAGER_CONFIG["check_interval_s"],
                minimum=2,
            ),
            "reconnect_after_failures": self._safe_int(
                network_manager.get("reconnect_after_failures", DEFAULT_NETWORK_MANAGER_CONFIG["reconnect_after_failures"]),
                DEFAULT_NETWORK_MANAGER_CONFIG["reconnect_after_failures"],
                minimum=1,
            ),
            "backend_timeout_s": self._safe_float(
                network_manager.get("backend_timeout_s", DEFAULT_NETWORK_MANAGER_CONFIG["backend_timeout_s"]),
                DEFAULT_NETWORK_MANAGER_CONFIG["backend_timeout_s"],
                minimum=0.5,
            ),
            "internet_host": str(network_manager.get("internet_host", DEFAULT_NETWORK_MANAGER_CONFIG["internet_host"])),
            "backend_url": str(network_manager.get("backend_url", DEFAULT_NETWORK_MANAGER_CONFIG["backend_url"])),
            "preferred_interface": str(network_manager.get("preferred_interface", DEFAULT_NETWORK_MANAGER_CONFIG["preferred_interface"])),
        }

        merged = dict(config)
        merged["api"] = {
            "base_urls": base_urls,
            "endpoint_receptor": endpoint,
            "endpoint_receptor_local": endpoint_local or DEFAULT_API_ENDPOINT_LOCAL,
            "endpoint_receptor_cloud": endpoint_cloud or DEFAULT_API_ENDPOINT_CLOUD,
            "endpoint_receptor_cloud_fallback": endpoint_cloud_fallback,
            "timeout_s": timeout_s,
            "headers": headers,
        }
        merged["admin"] = {"dni_admin": dni_admin}
        merged["atajos"] = {"promociones": normalized_hotkeys}
        merged["maquina"] = {
            "codigo_hardware": codigo_hardware,
            "tipo_maquina": 1,
            "hoppers": normalized_hoppers,
            "sensor_interrupts": sensor_interrupts_cfg,
        }
        merged["heartbeat"] = {"intervalo_s": intervalo_s}
        merged["mysql"] = mysql_cfg
        merged["updater"] = updater_cfg
        merged["network_manager"] = network_manager_cfg
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

