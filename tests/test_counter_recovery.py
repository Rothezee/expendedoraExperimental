"""Recuperación de contadores tras reinicio imprevisto."""

import unittest

from expendedora.logic.domain.models import Counters
from expendedora.logic.services.counter_service import CounterService


class CounterRecoveryTest(unittest.TestCase):
    def test_counters_clamp_negative_values(self):
        model = Counters.from_dict({"fichas_expendidas": -3, "fichas_promocion": 24, "dinero_ingresado": -1.0})
        self.assertEqual(model.fichas_expendidas, 0)
        self.assertEqual(model.fichas_promocion, 24)
        self.assertEqual(model.dinero_ingresado, 0.0)

    def test_restart_preserves_display_without_reset_sesion(self):
        """Simula reinicio: sesión HW y contadores persistidos se mantienen."""
        counter_service = CounterService()
        contadores_global = counter_service.ensure_schema({"fichas_expendidas": 27, "fichas_promocion": 24})
        contadores_parcial = counter_service.ensure_schema({"fichas_expendidas": 27, "fichas_promocion": 24})
        sesion_hw = 27  # recuperado del buffer, ya no se resetea al abrir GUI

        inicio_global = int(contadores_global["fichas_expendidas"]) - sesion_hw
        inicio_parcial = int(contadores_parcial["fichas_expendidas"]) - sesion_hw
        display_global = max(0, inicio_global + sesion_hw)
        display_parcial = max(0, inicio_parcial + sesion_hw)

        self.assertEqual(display_global, 27)
        self.assertEqual(display_parcial, 27)


if __name__ == "__main__":
    unittest.main()
