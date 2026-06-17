"""Recuperación de estado al arranque."""

from __future__ import annotations

from typing import Any, Dict, Optional

from expendedora.logic.services.machine_state import MachineState
from expendedora.persistence.json.config_repository import ConfigRepository
from expendedora.persistence.json.state_repository import StateRepository


class RecoveryService:
    def __init__(
        self,
        state_repo: StateRepository,
        config_repo: ConfigRepository,
        machine_state: MachineState,
    ) -> None:
        self._state_repo = state_repo
        self._config_repo = config_repo
        self._machine_state = machine_state
        self._recovered: Optional[dict] = None

    def recover_and_hydrate(self) -> Optional[dict]:
        try:
            snapshot = self._state_repo.recover()
            self._recovered = self._state_repo.get_recovered_counters(snapshot)
            self._machine_state.hydrate_from_recovery(self._recovered["buffer"])
            self._machine_state.restore_pending_lots(self._recovered.get("pending_lots"))
            cnt = self._recovered["contadores_global"]
            print(
                "[RECOVERY] Estado recuperado: "
                f"fichas_total={cnt.get('fichas_expendidas', 0)}, "
                f"restantes={cnt.get('fichas_restantes', 0)}, "
                f"dinero={cnt.get('dinero_ingresado', 0)}"
            )
            return self._recovered
        except Exception as exc:
            print(f"[RECOVERY] No se pudo recuperar estado: {exc}")
            self._recovered = None
            return None

    def get_recovered(self) -> Optional[dict]:
        return self._recovered
