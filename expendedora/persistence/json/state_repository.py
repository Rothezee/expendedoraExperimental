"""Fachada de persistencia de estado operativo (único writer de machine_state.json)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from expendedora.persistence.json import state_store
from expendedora.persistence.paths import CONFIG_FILE, REGISTRO_FILE, STATE_FILE


class StateRepository:
    def __init__(self, state_path: str = STATE_FILE, config_path: str = CONFIG_FILE):
        self.state_path = state_path
        self.config_path = config_path

    def recover(self, registro_path: str = REGISTRO_FILE) -> Dict[str, Any]:
        return state_store.recover_state(
            config_path=self.config_path,
            registro_path=registro_path,
            state_path=self.state_path,
        )

    def get_recovered_counters(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        return state_store.get_recovered_counters(snapshot)

    def build_snapshot(self, **kwargs) -> Dict[str, Any]:
        return state_store.build_snapshot(**kwargs)

    def load_snapshot(self) -> Optional[Dict[str, Any]]:
        return state_store.load_snapshot(self.state_path)

    def save_snapshot(
        self,
        snapshot: Dict[str, Any],
        *,
        sync_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return state_store.save_snapshot(
            snapshot,
            path=self.state_path,
            sync_config=sync_config,
            config_path=self.config_path,
        )

    def save_buffer_only(self, buffer_data: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
        return state_store.save_buffer_only(buffer_data, reason=reason)

    @staticmethod
    def default_buffer() -> Dict[str, Any]:
        return state_store.default_buffer()

    @staticmethod
    def buffer_keys():
        return state_store.BUFFER_PERSISTED_KEYS
