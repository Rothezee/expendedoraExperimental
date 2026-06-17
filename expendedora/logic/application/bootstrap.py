"""Composición e inyección de dependencias (único punto de wiring)."""

from __future__ import annotations

from expendedora.logic.application.app_controller import AppController
from expendedora.logic.services.counter_service import CounterService
from expendedora.logic.services.dispenser_service import DispenserService
from expendedora.logic.services.machine_state import MachineState
from expendedora.logic.services.network_manager_service import NetworkManagerService
from expendedora.logic.services.recovery_service import RecoveryService
from expendedora.logic.services.session_service import SessionService
from expendedora.logic.services.tolva_service import TolvaService
from expendedora.persistence.json.config_repository import ConfigRepository
from expendedora.persistence.json.state_repository import StateRepository
from expendedora.persistence.paths import CONFIG_FILE, migrate_legacy_data_files
from expendedora.persistence.mysql.auth_repository import AuthRepositoryMySQL
from expendedora.persistence.mysql.report_repository import ReportRepositoryMySQL
from expendedora.persistence.remote.session_api_repository import SessionApiRepository
from expendedora.persistence.remote.telemetry_repository import TelemetryRepository


def create_app_controller(config_path: str = CONFIG_FILE) -> AppController:
    migrate_legacy_data_files()
    config_repo = ConfigRepository(config_path)
    state_repo = StateRepository(config_path=config_path)
    telemetry_repo = TelemetryRepository(config_repo)
    auth_repo = AuthRepositoryMySQL(config_repo)
    session_api_repo = SessionApiRepository(config_repo, auth_repo)
    machine_state = MachineState(state_repo)
    tolva_service = TolvaService(config_repo)
    recovery_service = RecoveryService(state_repo, config_repo, machine_state)
    counter_service = CounterService()
    session_service = SessionService()
    network_service = NetworkManagerService(config_repo)
    report_repo = ReportRepositoryMySQL(config_repo)

    dispenser = DispenserService(
        machine_state,
        tolva_service,
        config_repo,
        telemetry_repo,
    )

    return AppController(
        config_repo=config_repo,
        state_repo=state_repo,
        machine_state=machine_state,
        tolva_service=tolva_service,
        recovery_service=recovery_service,
        dispenser_service=dispenser,
        telemetry_repo=telemetry_repo,
        session_api_repo=session_api_repo,
        counter_service=counter_service,
        session_service=session_service,
        network_service=network_service,
        report_repo=report_repo,
    )
