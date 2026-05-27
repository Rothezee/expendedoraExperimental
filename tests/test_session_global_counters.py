"""Validación de separación sesión (parcial) vs global para GUI/telemetría/cierre."""

import unittest

from services.counter_service import CounterService


class SessionGlobalCounterLogic(unittest.TestCase):
    def setUp(self):
        self.counter_service = CounterService()
        self.contadores_global = self.counter_service.default_counters()
        self.contadores_parcial = self.counter_service.default_counters()
        self.inicio_apertura_fichas = 0
        self.inicio_parcial_fichas = 0

    def _increment_operacion(self, key, amount=1):
        if key == "dinero_ingresado":
            self.contadores_parcial[key] = float(self.contadores_parcial.get(key, 0)) + float(amount)
            self.contadores_global[key] = float(self.contadores_global.get(key, 0)) + float(amount)
        else:
            self.contadores_parcial[key] = int(self.contadores_parcial.get(key, 0)) + int(amount)
            self.contadores_global[key] = int(self.contadores_global.get(key, 0)) + int(amount)

    def _sync_hw_fichas(self, fichas_expendidas_hw):
        self.contadores_parcial["fichas_expendidas"] = self.inicio_parcial_fichas + fichas_expendidas_hw
        self.contadores_global["fichas_expendidas"] = self.inicio_apertura_fichas + fichas_expendidas_hw

    def test_expender_actualiza_sesion_y_global(self):
        self._increment_operacion("dinero_ingresado", 1000)
        self._increment_operacion("fichas_normales", 2)
        self.assertEqual(self.contadores_parcial["dinero_ingresado"], 1000)
        self.assertEqual(self.contadores_global["dinero_ingresado"], 1000)
        self.assertEqual(self.contadores_parcial["fichas_normales"], 2)
        self.assertEqual(self.contadores_global["fichas_normales"], 2)

    def test_logout_resetea_sesion_mantiene_global(self):
        self._increment_operacion("dinero_ingresado", 1000)
        self._increment_operacion("fichas_normales", 2)
        self._sync_hw_fichas(2)

        global_snapshot = self.contadores_global.copy()

        # Simula cerrar_sesion: reset parcial, mantener global
        self.contadores_parcial = self.counter_service.default_counters()
        self.inicio_apertura_fichas = int(global_snapshot.get("fichas_expendidas", 0))
        self.inicio_parcial_fichas = 0

        self.assertEqual(self.contadores_parcial["dinero_ingresado"], 0)
        self.assertEqual(self.contadores_parcial["fichas_normales"], 0)
        self.assertEqual(self.contadores_global, global_snapshot)

    def test_telemetria_usa_valores_de_sesion(self):
        self._increment_operacion("dinero_ingresado", 1000)
        self._sync_hw_fichas(2)
        fichas_sesion = 2
        dinero_sesion = self.contadores_parcial["dinero_ingresado"]
        self.assertEqual(fichas_sesion, self.contadores_parcial["fichas_expendidas"])
        self.assertEqual(dinero_sesion, 1000)
        self.assertNotEqual(self.contadores_global["fichas_expendidas"], 0)

    def test_cierre_diario_usa_global(self):
        self._increment_operacion("dinero_ingresado", 2500)
        self._sync_hw_fichas(5)
        cierre_payload_source = self.contadores_global
        self.assertEqual(cierre_payload_source["dinero_ingresado"], 2500)
        self.assertEqual(cierre_payload_source["fichas_expendidas"], 5)

    def _simular_cierre_diario(self, fichas_expendidas_hw=0):
        """Simula realizar_cierre(): resetea solo global, preserva parcial."""
        cierre_payload = self.contadores_global.copy()
        self.contadores_global = self.counter_service.default_counters()
        self.inicio_apertura_fichas = -int(fichas_expendidas_hw)
        return cierre_payload

    def _simular_logout(self):
        contadores_subcierre = self.contadores_parcial.copy()
        self.contadores_parcial = self.counter_service.default_counters()
        self.inicio_apertura_fichas = int(self.contadores_global.get("fichas_expendidas", 0))
        self.inicio_parcial_fichas = 0
        return contadores_subcierre

    def test_cierre_diario_preserva_sesion_para_logout(self):
        self._increment_operacion("dinero_ingresado", 1000)
        self._increment_operacion("fichas_normales", 2)
        self._sync_hw_fichas(2)

        cierre_payload = self._simular_cierre_diario(fichas_expendidas_hw=2)

        self.assertEqual(cierre_payload["dinero_ingresado"], 1000)
        self.assertEqual(cierre_payload["fichas_expendidas"], 2)
        self.assertEqual(self.contadores_parcial["dinero_ingresado"], 1000)
        self.assertEqual(self.contadores_parcial["fichas_normales"], 2)
        self.assertEqual(self.contadores_parcial["fichas_expendidas"], 2)
        self.assertEqual(self.contadores_global["dinero_ingresado"], 0)

        subcierre = self._simular_logout()
        self.assertEqual(subcierre["dinero_ingresado"], 1000)
        self.assertEqual(subcierre["fichas_expendidas"], 2)

    def test_global_fichas_acumula_multi_sesion(self):
        self._sync_hw_fichas(5)
        self._simular_logout()

        self._sync_hw_fichas(3)
        self.assertEqual(self.contadores_parcial["fichas_expendidas"], 3)
        self.assertEqual(self.contadores_global["fichas_expendidas"], 8)

        cierre_payload = self._simular_cierre_diario(fichas_expendidas_hw=3)
        self.assertEqual(cierre_payload["fichas_expendidas"], 8)
        self.assertEqual(self.contadores_parcial["fichas_expendidas"], 3)


if __name__ == "__main__":
    unittest.main()
