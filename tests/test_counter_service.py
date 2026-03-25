import unittest

from services.counter_service import CounterService


class CounterServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = CounterService()

    def test_default_counters_have_required_keys(self):
        counters = self.service.default_counters()
        for key in (
            "fichas_expendidas",
            "dinero_ingresado",
            "promo1_contador",
            "promo2_contador",
            "promo3_contador",
            "fichas_restantes",
            "fichas_devolucion",
            "fichas_normales",
            "fichas_promocion",
            "fichas_cambio",
        ):
            self.assertIn(key, counters)

    def test_has_activity_detects_relevant_data(self):
        empty = self.service.default_counters()
        self.assertFalse(self.service.has_activity(empty))
        active = dict(empty)
        active["fichas_devolucion"] = 1
        self.assertTrue(self.service.has_activity(active))


if __name__ == "__main__":
    unittest.main()

