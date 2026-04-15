from typing import Any, Dict, List

import requests

from domain.models import TelemetryPayload


class TelemetryClient:
    def __init__(self, config_repository):
        self.config_repository = config_repository

    @staticmethod
    def _is_local_base(base_url: str) -> bool:
        lower = base_url.lower()
        return "127.0.0.1" in lower or "localhost" in lower

    @staticmethod
    def _is_cloud_base(base_url: str) -> bool:
        return "app.maquinasbonus.com" in base_url.lower()

    @staticmethod
    def _build_urls(config: Dict[str, Any]) -> List[str]:
        api = config.get("api", {})
        base_urls = api.get("base_urls", [])
        endpoint = str(api.get("endpoint_receptor", "") or "").strip().lstrip("/")
        endpoint_local = str(api.get("endpoint_receptor_local", endpoint) or "").strip().lstrip("/")
        endpoint_cloud = str(api.get("endpoint_receptor_cloud", endpoint) or "").strip().lstrip("/")
        urls: List[str] = []
        for base in base_urls:
            normalized_base = str(base).strip().rstrip("/")
            if not normalized_base:
                continue
            target_endpoint = endpoint
            if TelemetryClient._is_local_base(normalized_base) and endpoint_local:
                target_endpoint = endpoint_local
            elif TelemetryClient._is_cloud_base(normalized_base) and endpoint_cloud:
                target_endpoint = endpoint_cloud
            urls.append(f"{normalized_base}/{target_endpoint}" if target_endpoint else normalized_base)
        return urls

    @staticmethod
    def build_heartbeat_body(config: Dict[str, Any]) -> Dict[str, Any]:
        maquina = config.get("maquina", {})
        admin = config.get("admin", {})
        return TelemetryPayload(
            action=1,
            dni_admin=str(admin.get("dni_admin", "")),
            codigo_hardware=str(maquina.get("codigo_hardware", "")),
            tipo_maquina=1,
        ).to_dict()

    @staticmethod
    def build_telemetry_body(config: Dict[str, Any], fichas: int, dinero: float) -> Dict[str, Any]:
        maquina = config.get("maquina", {})
        admin = config.get("admin", {})
        return TelemetryPayload(
            action=2,
            dni_admin=str(admin.get("dni_admin", "")),
            codigo_hardware=str(maquina.get("codigo_hardware", "")),
            tipo_maquina=1,
            payload={"fichas": int(fichas), "dinero": float(dinero)},
        ).to_dict()

    def post_body(self, body: Dict[str, Any], context: str = "api_receptor") -> None:
        config = self.config_repository.load()
        timeout_s = config.get("api", {}).get("timeout_s", 5)
        for url in self._build_urls(config):
            try:
                response = requests.post(url, json=body, timeout=timeout_s)
                print(f"[API] {context} -> {url} [{response.status_code}]")
            except requests.RequestException as exc:
                print(f"[API ERROR] {context} -> {url}: {exc}")

