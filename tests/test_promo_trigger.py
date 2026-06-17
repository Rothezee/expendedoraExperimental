"""Tests de activación de promociones (sin hardware)."""

import time
import unittest
from unittest.mock import MagicMock, patch

from expendedora.interface.gui.mixins.operations_mixin import OperationsMixin


class _PromoGuiStub(OperationsMixin):
    def __init__(self):
        self.promociones = {
            "Promo 1": {"precio": 10000.0, "fichas": 24},
            "Promo 3": {"precio": 25000.0, "fichas": 70},
        }
        self._promo_last_trigger_ts = {}
        self._ms = MagicMock()
        self._ms.get_fichas_restantes.return_value = 0
        self.contadores = {
            "fichas_restantes": 0,
            "dinero_ingresado": 0.0,
            "promo3_contador": 0,
        }
        self.contadores_labels = {}
        self.contadores_parcial = {"dinero_ingresado": 0.0}
        self.contadores_global = {"dinero_ingresado": 0.0}


class PromoTriggerTest(unittest.TestCase):
    def test_fichas_desde_config_entero(self):
        gui = _PromoGuiStub()
        self.assertEqual(gui._promo_fichas_configuradas("Promo 3"), 70)
        gui.promociones["Promo 3"]["fichas"] = 70.0
        self.assertEqual(gui._promo_fichas_configuradas("Promo 3"), 70)

    def test_rebote_ignora_segundo_disparo_rapido(self):
        gui = _PromoGuiStub()
        self.assertFalse(gui._promo_rebote_activo("Promo 1"))
        self.assertTrue(gui._promo_rebote_activo("Promo 1"))

    def test_rebote_permite_despues_de_debounce(self):
        gui = _PromoGuiStub()
        gui._promo_last_trigger_ts["Promo 1"] = time.time() - 2.0
        self.assertFalse(gui._promo_rebote_activo("Promo 1"))

    @patch("expendedora.interface.gui.mixins.operations_mixin.messagebox")
    def test_simular_promo_suma_solo_fichas_config(self, messagebox_mock):
        gui = _PromoGuiStub()
        gui._increment_contador_operacion = MagicMock()
        gui._ms.register_pending_lot = MagicMock()
        gui.actualizar_contadores_gui = MagicMock()
        gui._persistir_estado_critico = MagicMock()
        gui.actualizar_estado_operacion_ui = MagicMock()
        gui.contadores_labels = {
            "dinero_ingresado": MagicMock(),
            "promo3_contador": MagicMock(),
        }

        def _process():
            gui._ms.get_fichas_restantes.return_value = 70

        gui._ms.process_gui_commands.side_effect = _process

        gui.simular_promo("Promo 3")

        put_call = gui._ms.gui_to_core_queue.put.call_args[0][0]
        self.assertEqual(put_call["fichas"], 70)
        self.assertEqual(put_call["promo_num"], 3)
        messagebox_mock.askyesno.assert_not_called()

    def test_numeros_raros_son_multiplos_plausibles(self):
        """Documenta la hipótesis: 900≈70×13, 100≈24×4 (rebote de tecla + suma)."""
        self.assertEqual(70 * 13, 910)
        self.assertAlmostEqual(900 / 70, 12.86, places=1)
        self.assertEqual(24 * 4, 96)
        self.assertAlmostEqual(100 / 24, 4.17, places=1)


if __name__ == "__main__":
    unittest.main()
