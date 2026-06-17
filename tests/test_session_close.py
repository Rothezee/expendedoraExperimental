"""Tests de payloads y persistencia de cierres."""

import unittest

from expendedora.logic.application.bootstrap import create_app_controller
from expendedora.logic.domain.models import Counters
from expendedora.logic.services.session_service import SessionService


class SessionCloseTest(unittest.TestCase):
    def test_partial_close_uses_numeric_cajero_id_only(self):
        payload = SessionService.build_partial_close(
            "EXP_1",
            Counters(fichas_expendidas=5, dinero_ingresado=100).to_dict(),
            "cajero_local",
            cashier_id=42,
        )
        self.assertEqual(payload["id_cajero"], 42)
        self.assertEqual(payload["usuario_cajero"], "cajero_local")

    def test_partial_close_without_cajero_id_omits_numeric_field(self):
        payload = SessionService.build_partial_close(
            "EXP_1",
            Counters().to_dict(),
            "cajero_local",
            cashier_id=None,
        )
        self.assertNotIn("id_cajero", payload)
        self.assertEqual(payload["usuario_cajero"], "cajero_local")

    def test_persist_snapshot_guarda_operacion(self):
        app = create_app_controller()
        app.persist_snapshot(
            contadores_global=Counters().to_dict(),
            contadores_parcial=Counters().to_dict(),
            operacion={"ultima_apertura_fecha": "2026-06-09"},
            reason="test_operacion",
        )
        cfg = app.load_config()
        self.assertEqual(cfg.get("operacion", {}).get("ultima_apertura_fecha"), "2026-06-09")

    def test_daily_close_sets_tipo_evento(self):
        payload = SessionService.build_daily_close("DEV1", Counters(dinero_ingresado=50).to_dict())
        self.assertEqual(payload["tipo_evento"], "cierre")
        self.assertEqual(payload["dinero_ingresado"], 50)
