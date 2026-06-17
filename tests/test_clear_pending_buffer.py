"""Tests para vaciar buffer de dispensado."""

import unittest
from unittest.mock import MagicMock

from expendedora.logic.services.machine_state import MachineState


class ClearPendingBufferTest(unittest.TestCase):
    def test_clear_pending_dispense_zeros_buffer(self):
        from expendedora.logic.hardware.serial_bridge import SerialBridge

        tolva = MagicMock()
        tolva.bloqueo_emergencia = False
        tolva._tolvas_lock = __import__("threading").Lock()
        tolva._tolvas_trabadas = set()

        ms = MachineState()
        ms.set_fichas_restantes(5, immediate=False)
        bridge = SerialBridge(ms, tolva)
        bridge._backend = None

        bridge.clear_pending_dispense()

        self.assertEqual(ms.get_fichas_restantes(), 0)
        self.assertFalse(ms.get_motor_activo())
        self.assertEqual(ms.get_motor_direccion(), "detenido")
        self.assertFalse(tolva.bloqueo_emergencia)

    def test_vaciar_buffer_via_app_controller(self):
        from expendedora.logic.application.bootstrap import create_app_controller

        app = create_app_controller()
        app.machine_state.set_fichas_restantes(3, immediate=False)
        app.machine_state.register_pending_lot(3, fichas_normales=3)
        revert = app.vaciar_buffer()
        self.assertEqual(app.machine_state.get_fichas_restantes(), 0)
        self.assertEqual(revert.get("fichas_normales", 0), 0)
        self.assertEqual(revert.get("fichas_dispensadas", 0), 0)


class PendingLotsLedgerTest(unittest.TestCase):
    def setUp(self):
        self.ms = MachineState()

    def test_revert_sin_dispensar_solo_dinero(self):
        self.ms.register_pending_lot(5, dinero_ingresado=50.0, fichas_normales=5)
        revert = self.ms.revert_all_pending_lots()
        self.assertEqual(revert.get("fichas_normales", 0), 0)
        self.assertEqual(revert.get("fichas_dispensadas", 0), 0)
        self.assertAlmostEqual(revert["dinero_ingresado"], 50.0)

    def test_consume_encola_atribucion_por_token(self):
        self.ms.register_pending_lot(3, fichas_normales=3)
        self.ms.consume_pending_lots(1)
        attrs = self.ms.drain_token_attributions()
        self.assertEqual(len(attrs), 1)
        self.assertEqual(attrs[0].get("fichas_normales"), 1)

    def test_promo_trabada_dinero_completo_fichas_solo_salidas(self):
        """Promo $500 / 10 fichas, 4 salieron: vaciar revierte $500 y 4 fichas."""
        self.ms.register_pending_lot(
            10,
            dinero_ingresado=500.0,
            fichas_promocion=10,
            promo1_contador=1,
        )
        for _ in range(4):
            self.ms.consume_pending_lots(1)
        self.ms.registrar_fichas_expendidas(4, immediate=False)
        self.ms.set_fichas_restantes(6, immediate=False)

        revert = self.ms.revert_all_pending_lots()

        self.assertAlmostEqual(revert["dinero_ingresado"], 500.0)
        self.assertEqual(revert["promo1_contador"], 1)
        self.assertEqual(revert["fichas_dispensadas"], 4)
        self.assertEqual(revert["fichas_promocion"], 4)
        self.assertEqual(revert.get("fichas_normales", 0), 0)

        self.ms.revert_fichas_sesion_hw(revert["fichas_dispensadas"], immediate=False)
        self.assertEqual(self.ms.get_fichas_sesion(), 0)

    def test_vaciar_sin_dispensar_revierte_solo_dinero(self):
        from expendedora.logic.application.bootstrap import create_app_controller

        app = create_app_controller()
        cantidad = 5
        dinero = 500.0
        app.machine_state.register_pending_lot(
            cantidad,
            dinero_ingresado=dinero,
            fichas_normales=cantidad,
        )
        app.machine_state.set_fichas_restantes(cantidad, immediate=False)

        revert = app.vaciar_buffer()
        self.assertAlmostEqual(revert["dinero_ingresado"], dinero)
        self.assertEqual(revert.get("fichas_normales", 0), 0)
        self.assertEqual(revert.get("fichas_dispensadas", 0), 0)
