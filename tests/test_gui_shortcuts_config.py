import unittest
import tempfile
import json
from pathlib import Path

from expendedora.interface.gui.app import ExpendedoraGUI
from expendedora.interface.gui.constants import DEFAULT_PROMO_HOTKEYS


class GuiShortcutsConfigTest(unittest.TestCase):
    def test_normalizar_atajos_respeta_lista_vacia(self):
        gui = ExpendedoraGUI.__new__(ExpendedoraGUI)
        normalized = gui._normalizar_atajos_promociones(
            {
                "Promo 1": [],
                "Promo 2": ["<KP_Multiply>"],
                "Promo 3": [],
            }
        )
        self.assertEqual(normalized["Promo 1"], [])
        self.assertEqual(normalized["Promo 2"], ["<KP_Multiply>"])
        self.assertEqual(normalized["Promo 3"], [])

    def test_normalizar_atajos_rellena_defaults_si_config_invalida(self):
        gui = ExpendedoraGUI.__new__(ExpendedoraGUI)
        normalized = gui._normalizar_atajos_promociones(
            {
                "Promo 1": None,
                "Promo 2": "<KP_Multiply>",
                "Promo 3": 123,
            }
        )
        self.assertEqual(normalized["Promo 1"], DEFAULT_PROMO_HOTKEYS["Promo 1"])
        self.assertEqual(normalized["Promo 2"], ["<KP_Multiply>"])
        self.assertEqual(normalized["Promo 3"], DEFAULT_PROMO_HOTKEYS["Promo 3"])

    def test_shortcuts_file_roundtrip(self):
        gui = ExpendedoraGUI.__new__(ExpendedoraGUI)
        with tempfile.TemporaryDirectory() as tmp:
            shortcuts_path = Path(tmp) / "atajos_promociones.json"
            gui.shortcuts_file = str(shortcuts_path)
            gui.atajos_promociones = {
                "Promo 1": [],
                "Promo 2": ["<KP_Multiply>"],
                "Promo 3": ["<minus>"],
            }
            gui._save_shortcuts_to_file()
            self.assertTrue(shortcuts_path.exists())
            loaded_json = json.loads(shortcuts_path.read_text(encoding="utf-8"))
            self.assertIn("promociones", loaded_json)

            loaded = gui._load_shortcuts_from_file()
            self.assertEqual(loaded["Promo 1"], [])
            self.assertEqual(loaded["Promo 2"], ["<KP_Multiply>"])
            self.assertEqual(loaded["Promo 3"], ["<minus>"])


if __name__ == "__main__":
    unittest.main()
