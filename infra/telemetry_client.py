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
        return [target["url"] for target in TelemetryClient._build_targets(config)]

    @staticmethod
    def _build_targets(config: Dict[str, Any]) -> List[Dict[str, str]]:
        api = config.get("api", {})
        base_urls = api.get("base_urls", [])
        endpoint = str(api.get("endpoint_receptor", "") or "").strip().lstrip("/")
        endpoint_local = str(api.get("endpoint_receptor_local", endpoint) or "").strip().lstrip("/")
        endpoint_cloud = str(api.get("endpoint_receptor_cloud", endpoint) or "").strip().lstrip("/")
        endpoint_cloud_fallback = str(
            api.get("endpoint_receptor_cloud_fallback", endpoint or endpoint_local) or ""
        ).strip().lstrip("/")
        targets: List[Dict[str, str]] = []
        for base in base_urls:
            normalized_base = str(base).strip().rstrip("/")
            if not normalized_base:
                continue
            target_endpoint = endpoint
            fallback_endpoint = ""
            if TelemetryClient._is_local_base(normalized_base) and endpoint_local:
                target_endpoint = endpoint_local
            elif TelemetryClient._is_cloud_base(normalized_base) and endpoint_cloud:
                target_endpoint = endpoint_cloud
                if endpoint_cloud_fallback and endpoint_cloud_fallback != target_endpoint:
                    fallback_endpoint = endpoint_cloud_fallback
            target_url = f"{normalized_base}/{target_endpoint}" if target_endpoint else normalized_base
            fallback_url = f"{normalized_base}/{fallback_endpoint}" if fallback_endpoint else ""
            targets.append({"url": target_url, "fallback_url": fallback_url})
        return targets

    @staticmethod
    def _build_headers(config: Dict[str, Any]) -> Dict[str, str]:
        api = config.get("api", {})
        raw_headers = api.get("headers", {})
        headers: Dict[str, str] = {}
        if isinstance(raw_headers, dict):
            for key, value in raw_headers.items():
                key_str = str(key).strip()
                value_str = str(value).strip()
                if key_str and value_str:
                    headers[key_str] = value_str
        headers.setdefault("User-Agent", "ExpendedoraTelemetry/1.0")
        return headers

    @staticmethod
    def _log_http_result(context: str, url: str, response: requests.Response) -> None:
        print(f"[API] {context} -> {url} [{response.status_code}]")
        if response.status_code < 400:
            return

        body_preview = str(response.text or "").strip().replace("\n", " ")
        if len(body_preview) > 180:
            body_preview = f"{body_preview[:180]}..."
        server = response.headers.get("Server", "-")
        auth_hint = response.headers.get("WWW-Authenticate", "-")
        print(
            f"[API WARN] {context} -> {url} status={response.status_code} "
            f"server={server} auth={auth_hint} body='{body_preview or '-'}'"
        )

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
            fichas=int(fichas),
            dinero=float(dinero),
        ).to_dict()

    def post_body(self, body: Dict[str, Any], context: str = "api_receptor") -> None:
        config = self.config_repository.load()
        timeout_s = config.get("api", {}).get("timeout_s", 5)
        headers = self._build_headers(config)
        for target in self._build_targets(config):
            url = target["url"]
            try:
                response = requests.post(url, json=body, timeout=timeout_s, headers=headers)
                self._log_http_result(context, url, response)

                fallback_url = target.get("fallback_url", "")
                if fallback_url and response.status_code in (403, 404):
                    print(f"[API] {context} -> fallback cloud endpoint {fallback_url}")
                    fallback_response = requests.post(
                        fallback_url,
                        json=body,
                        timeout=timeout_s,
                        headers=headers,
                    )
                    self._log_http_result(f"{context} (fallback)", fallback_url, fallback_response)
            except requests.RequestException as exc:
                print(f"[API ERROR] {context} -> {url}: {exc}")

