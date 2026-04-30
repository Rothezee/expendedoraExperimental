import tempfile
import unittest
from pathlib import Path

from infra.config_repository import ConfigRepository


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
        self.assertEqual(len(normalized["maquina"]["hoppers"]), 3)
        self.assertIn("atajos", normalized)
        self.assertIn("promociones", normalized["atajos"])
        self.assertIn("Promo 1", normalized["atajos"]["promociones"])
        self.assertIn("calibracion", normalized["maquina"]["hoppers"][0])

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
            self.assertEqual(len(loaded["maquina"]["hoppers"]), 3)
            self.assertIn("atajos", loaded)
            self.assertIn("promociones", loaded["atajos"])
            self.assertIn("Promo 2", loaded["atajos"]["promociones"])
            self.assertIn("calibracion", loaded["maquina"]["hoppers"][1])

    def test_normalize_mysql_null_password_no_string_none(self):
        repo = ConfigRepository("config.json")
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


if __name__ == "__main__":
    unittest.main()

