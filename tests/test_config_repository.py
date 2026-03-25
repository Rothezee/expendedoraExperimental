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
        self.assertEqual(normalized["updater"]["branch"], "main")
        self.assertEqual(normalized["updater"]["remote"], "origin")

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            repo = ConfigRepository(str(config_path))
            repo.save({"device_id": "EXP_TEST"})
            loaded = repo.load()
            self.assertEqual(loaded["device_id"], "EXP_TEST")
            self.assertEqual(loaded["maquina"]["codigo_hardware"], "EXP_TEST")
            self.assertIn("preserve_files", loaded["updater"])


if __name__ == "__main__":
    unittest.main()

