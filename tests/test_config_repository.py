import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expendedora.persistence.json.config_repository import ConfigRepository


class ConfigRepositoryTest(unittest.TestCase):
    def test_normalize_legacy_config_maps_device_and_defaults(self):
        repo = ConfigRepository("config.json")
        legacy = {"device_id": "EXP_1", "valor_ficha": 1000.0}
        normalized = repo.normalize(legacy)
        self.assertEqual(normalized["maquina"]["codigo_hardware"], "EXP_1")
        self.assertEqual(normalized["admin"]["dni_admin"], "00000000")
        self.assertEqual(normalized["heartbeat"]["intervalo_s"], 600)
        self.assertIn("mysql", normalized)
        self.assertIn("updater", normalized)
        self.assertIn("network_manager", normalized)
        self.assertEqual(normalized["updater"]["branch"], "main")
        self.assertEqual(normalized["updater"]["remote"], "origin")
        self.assertTrue(normalized["network_manager"]["enabled"])
        self.assertIn("local", normalized["mysql"])
        self.assertIn("production", normalized["mysql"])
        self.assertEqual(normalized["mysql"]["active"], "local")
        self.assertIn("hoppers", normalized["maquina"])
        self.assertEqual(len(normalized["maquina"]["hoppers"]), 1)
        self.assertEqual(normalized["maquina"]["hoppers"][0]["nombre"], "Tolva 1")
        self.assertIn("atajos", normalized)
        self.assertIn("promociones", normalized["atajos"])
        self.assertIn("Promo 1", normalized["atajos"]["promociones"])
        self.assertIn("calibracion", normalized["maquina"]["hoppers"][0])
        self.assertIn("hardware", normalized)
        self.assertEqual(normalized["hardware"]["backend"], "esp32_serial")
        self.assertIn("esp32", normalized["hardware"])

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            repo = ConfigRepository(str(config_path))
            repo.save({"device_id": "EXP_TEST"})
            loaded = repo.load()
            self.assertEqual(loaded["device_id"], "EXP_TEST")
            self.assertEqual(loaded["maquina"]["codigo_hardware"], "EXP_TEST")
            self.assertIn("preserve_files", loaded["updater"])
            self.assertIn("network_manager", loaded)
            self.assertIn("check_interval_s", loaded["network_manager"])
            self.assertIn("local", loaded["mysql"])
            self.assertEqual(len(loaded["maquina"]["hoppers"]), 1)
            self.assertIn("atajos", loaded)
            self.assertIn("promociones", loaded["atajos"])
            self.assertIn("Promo 2", loaded["atajos"]["promociones"])
            self.assertIn("calibracion", loaded["maquina"]["hoppers"][0])

    def test_normalize_mysql_null_password_no_string_none(self):
        repo = ConfigRepository("config.json")
        env_limpio = {k: v for k, v in os.environ.items() if not k.startswith("MYSQL_")}
        with patch.dict(os.environ, env_limpio, clear=True):
            normalized = repo.normalize(
                {
                    "mysql": {
                        "active": "local",
                        "fallback_to_secondary": True,
                        "local": {
                            "host": "localhost",
                            "port": 3306,
                            "user": "root",
                            "password": None,
                            "database": "sistemadeadministracion",
                        },
                        "production": {
                            "host": "remote.example",
                            "port": 3306,
                            "user": "u",
                            "password": "secret",
                            "database": "db",
                        },
                    },
                }
            )
        self.assertEqual(normalized["mysql"]["local"]["password"], "")
        self.assertFalse(normalized["mysql"]["local"]["password"] == "None")

    def test_iter_mysql_targets_legacy_flat_from_section(self):
        targets = ConfigRepository.iter_mysql_targets_from_section(
            {
                "host": "127.0.0.1",
                "port": 3307,
                "user": "legacy_user",
                "password": "",
                "database": "legacy_db",
            }
        )
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["host"], "127.0.0.1")
        self.assertEqual(targets[0]["port"], 3307)
        self.assertEqual(targets[0]["database"], "legacy_db")

    def test_normalize_migrates_legacy_counter_keys_to_two_domains(self):
        repo = ConfigRepository("config.json")
        normalized = repo.normalize(
            {
                "contadores": {"fichas_expendidas": 3, "dinero_ingresado": 1000.0},
                "contadores_apertura": {"fichas_expendidas": 7, "dinero_ingresado": 2000.0},
                "contadores_parciales": {"fichas_expendidas": 2, "dinero_ingresado": 500.0},
            }
        )
        self.assertIn("contadores_global", normalized)
        self.assertIn("contadores_parcial", normalized)
        self.assertNotIn("contadores", normalized)
        self.assertNotIn("contadores_apertura", normalized)
        self.assertNotIn("contadores_parciales", normalized)
        self.assertEqual(normalized["contadores_global"]["fichas_expendidas"], 7)
        self.assertEqual(normalized["contadores_parcial"]["fichas_expendidas"], 2)

    def test_normalize_shortcuts_respects_explicit_empty_lists(self):
        repo = ConfigRepository("config.json")
        normalized = repo.normalize(
            {
                "atajos": {
                    "promociones": {
                        "Promo 1": [],
                        "Promo 2": ["<KP_Multiply>"],
                        "Promo 3": [],
                    }
                }
            }
        )
        promos = normalized["atajos"]["promociones"]
        self.assertEqual(promos["Promo 1"], [])
        self.assertEqual(promos["Promo 2"], ["<KP_Multiply>"])
        self.assertEqual(promos["Promo 3"], [])

    def test_default_hoppers_pins_match_firmware(self):
        repo = ConfigRepository("config.json")
        normalized = repo.normalize({})
        hopper = normalized["maquina"]["hoppers"][0]
        self.assertEqual(hopper["motor_pin"], 10)
        self.assertEqual(hopper["motor_pin_rev"], 12)
        self.assertEqual(hopper["sensor_pin"], 9)
        self.assertTrue(hopper["sensor_blocked_high"])


if __name__ == "__main__":
    unittest.main()

