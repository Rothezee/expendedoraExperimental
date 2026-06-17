"""HTTP remoto: cierres diarios y subcierres de sesión."""

from __future__ import annotations

import threading
from typing import Any, Dict, Iterable, Optional, Tuple

import requests


class SessionApiRepository:
    def __init__(self, config_repository, auth_repository=None) -> None:
        self._config_repo = config_repository
        self._auth_repo = auth_repository

    def _api_timeout_s(self) -> float:
        config = self._config_repo.load()
        return float(config.get("api", {}).get("timeout_s", 5))

    def _api_headers(self) -> Dict[str, str]:
        from expendedora.persistence.remote.telemetry_repository import TelemetryRepository

        return TelemetryRepository._build_headers(self._config_repo.load())

    @staticmethod
    def _is_local_base_url(base_url: str) -> bool:
        lower = str(base_url or "").lower()
        return "127.0.0.1" in lower or "localhost" in lower

    def _iter_backend_targets(self, local_path: str, cloud_path: str) -> Iterable[Tuple[str, str]]:
        config = self._config_repo.load()
        api = config.get("api", {})
        base_urls = api.get("base_urls", ["http://127.0.0.1", "https://app.maquinasbonus.com"])
        if isinstance(base_urls, str):
            base_urls = [base_urls]
        for base in base_urls:
            normalized = str(base).strip().rstrip("/")
            if not normalized:
                continue
            if self._is_local_base_url(normalized):
                endpoint = str(local_path).strip().lstrip("/")
                scope = "local"
            else:
                endpoint = str(cloud_path).strip().lstrip("/")
                scope = "cloud"
            url = f"{normalized}/{endpoint}" if endpoint else normalized
            yield url, scope

    @staticmethod
    def _cashier_username_from_payload(payload: dict) -> str:
        for key in ("usuario_cajero", "username_cajero", "employee_id", "nombre_cajero"):
            value = str(payload.get(key, "") or "").strip()
            if value:
                return value
        return ""

    def _adapt_payload_for_scope(self, payload: dict, scope: str) -> dict:
        """
        Local y remoto pueden tener distintos id_cajero para el mismo usuario_cajero.
        - local: conserva id del login (MySQL local).
        - cloud: resuelve id en producción por usuario; nunca reutiliza id local.
        """
        if not isinstance(payload, dict):
            return payload
        if "usuario_cajero" not in payload and "id_cajero" not in payload:
            return payload

        username = self._cashier_username_from_payload(payload)
        adapted = dict(payload)

        if scope == "local":
            if username and self._auth_repo is not None:
                local_id = self._auth_repo.resolve_cashier_id(username, production_only=False)
                if local_id is not None:
                    adapted["id_cajero"] = local_id
            return adapted

        # Cloud / remoto
        local_id = adapted.pop("id_cajero", None)
        if not username:
            return adapted

        remote_id: Optional[int] = None
        if self._auth_repo is not None:
            try:
                remote_id = self._auth_repo.resolve_cashier_id(username, production_only=True)
            except Exception as exc:
                print(f"[NET] cloud: no se resolvió id_cajero remoto ({type(exc).__name__})")

        if remote_id is not None:
            adapted["id_cajero"] = remote_id
            if local_id is not None and int(local_id) != int(remote_id):
                print(
                    f"[NET] cloud: id_cajero alineado usuario={username!r} "
                    f"local={local_id} -> remoto={remote_id}"
                )
        else:
            print(
                f"[NET] cloud: sin id_cajero remoto para usuario={username!r}; "
                "enviando solo campos de usuario (sin id local)"
            )
        return adapted

    def post_event_async(
        self,
        *,
        local_path: str,
        cloud_path: str,
        payload: dict,
        descripcion: str,
        retry_without_cashier_id: bool = False,
    ) -> None:
        timeout_s = self._api_timeout_s()
        headers = self._api_headers()

        def _enviar(url: str, scope: str) -> None:
            body = self._adapt_payload_for_scope(payload, scope)
            try:
                resp = requests.post(url, json=body, timeout=timeout_s, headers=headers)
                print(f"[NET] {descripcion} {scope} -> {resp.status_code}")
                body_preview = ""
                if resp.status_code >= 400:
                    body_preview = str(resp.text or "").strip().replace("\n", " ")
                    if len(body_preview) > 240:
                        body_preview = f"{body_preview[:240]}..."
                    print(f"[NET WARN] {descripcion} {scope} body: {body_preview or '-'}")
                if (
                    retry_without_cashier_id
                    and resp.status_code == 404
                    and "cajero no encontrado" in (body_preview or "").lower()
                    and isinstance(body, dict)
                    and "id_cajero" in body
                ):
                    retry_payload = dict(body)
                    retry_payload.pop("id_cajero", None)
                    retry_resp = requests.post(url, json=retry_payload, timeout=timeout_s, headers=headers)
                    print(f"[NET] {descripcion} {scope} (retry sin id_cajero) -> {retry_resp.status_code}")
            except requests.RequestException as exc:
                print(f"[NET ERROR] {descripcion} {scope}: {exc}")

        for url, scope in self._iter_backend_targets(local_path, cloud_path):
            threading.Thread(target=_enviar, args=(url, scope), daemon=True).start()
