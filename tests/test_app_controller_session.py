"""Tests de sesión vía AppController."""

import unittest

from expendedora.logic.application.bootstrap import create_app_controller
from expendedora.logic.domain.models import Counters


class AppControllerSessionTest(unittest.TestCase):
    def test_persist_snapshot_guarda_contadores_global(self):
        app = create_app_controller()
        base = Counters().to_dict()
        base["fichas_expendidas"] = 5
        parcial = Counters().to_dict()
        parcial["fichas_expendidas"] = 3
        app.persist_snapshot(
            contadores_global=base,
            contadores_parcial=parcial,
            reason="test_sesion",
        )
        cfg = app.load_config()
        self.assertEqual(int(cfg["contadores_global"]["fichas_expendidas"]), 5)
        self.assertEqual(int(cfg["contadores_parcial"]["fichas_expendidas"]), 3)
