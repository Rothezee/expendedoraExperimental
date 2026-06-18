"""Tests del manual Markdown y escenarios de ayuda."""

import tkinter as tk
import unittest
from unittest.mock import MagicMock, patch

from expendedora.interface.gui.help_content import HELP_SCENARIOS
from expendedora.interface.gui.manual_markdown import (
    DEFAULT_MANUAL_PATH,
    load_manual_markdown,
    render_markdown,
)
from expendedora.interface.gui.mixins.help_mixin import HelpMixin


class HelpContentTest(unittest.TestCase):
    def test_manual_md_exists(self):
        self.assertTrue(DEFAULT_MANUAL_PATH.is_file())
        content = load_manual_markdown()
        self.assertIn("# Manual de usuario", content)
        self.assertIn("## Cómo vender fichas", content)
        self.assertIn("## Menú Ayuda", content)
        self.assertNotIn("```mermaid", content)

    def test_help_scenarios_have_handlers(self):
        self.assertEqual(len(HELP_SCENARIOS), 5)
        for scenario in HELP_SCENARIOS:
            self.assertTrue(scenario.label)
            self.assertTrue(scenario.action.startswith("help_"))
            self.assertTrue(hasattr(HelpMixin, scenario.action))

    def test_manual_screenshots_exist(self):
        shots_dir = DEFAULT_MANUAL_PATH.parent / "screenshots"
        for name in ("inicio.png", "contadores.png", "cierre.png"):
            self.assertTrue((shots_dir / name).is_file(), f"Falta captura {name}")

    def test_render_markdown_applies_tags(self):
        root = tk.Tk()
        root.withdraw()
        try:
            text = tk.Text(root)
            sample = "# Titulo\n\n**negrita** y `codigo`\n\n- item\n"
            render_markdown(text, sample)
            content = text.get("1.0", "end")
            self.assertIn("Titulo", content)
            self.assertIn("negrita", content)
            self.assertIn("h1", text.tag_names("1.0"))
        finally:
            root.destroy()

    def test_render_markdown_embeds_image(self):
        root = tk.Tk()
        root.withdraw()
        try:
            text = tk.Text(root)
            shot = DEFAULT_MANUAL_PATH.parent / "screenshots" / "inicio.png"
            if not shot.is_file():
                self.skipTest("sin capturas generadas")
            md = f"## Seccion\n\n![Inicio](screenshots/inicio.png)\n"
            render_markdown(text, md, md_base_dir=DEFAULT_MANUAL_PATH.parent)
            self.assertTrue(getattr(text, "_manual_images", []))
        finally:
            root.destroy()

    def test_run_help_scenario_unknown_action(self):
        class FakeGui(HelpMixin):
            pass

        gui = FakeGui()
        with patch(
            "expendedora.interface.gui.mixins.help_mixin.messagebox.showerror"
        ) as show_error:
            gui._run_help_scenario("help_inexistente")
            show_error.assert_called_once()

    def test_help_arduino_sin_conexion_skips_extra_confirm(self):
        gui = MagicMock()
        gui.app.get_serial_status.return_value = {"connected": False}
        gui._on_click_status_arduino = MagicMock()
        HelpMixin.help_arduino_sin_conexion(gui)
        gui._on_click_status_arduino.assert_called_once_with(confirm=False)


if __name__ == "__main__":
    unittest.main()
