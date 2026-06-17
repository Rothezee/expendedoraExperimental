"""Tests del manual Markdown y escenarios de ayuda."""

import tkinter as tk
import unittest

from expendedora.interface.gui.help_content import (
    HELP_PLACEHOLDER,
    HELP_SCENARIOS,
    help_combo_values,
)
from expendedora.interface.gui.manual_markdown import (
    DEFAULT_MANUAL_PATH,
    load_manual_markdown,
    render_markdown,
)


class HelpContentTest(unittest.TestCase):
    def test_manual_md_exists(self):
        self.assertTrue(DEFAULT_MANUAL_PATH.is_file())
        content = load_manual_markdown()
        self.assertIn("# Manual de usuario", content)
        self.assertIn("## Cómo vender fichas", content)
        self.assertNotIn("```mermaid", content)

    def test_help_scenarios_have_actions(self):
        self.assertGreaterEqual(len(HELP_SCENARIOS), 2)
        for scenario in HELP_SCENARIOS:
            self.assertTrue(scenario.label)
            self.assertTrue(scenario.action.startswith("help_"))

    def test_combo_starts_with_placeholder(self):
        values = help_combo_values()
        self.assertEqual(values[0], HELP_PLACEHOLDER)
        self.assertEqual(len(values), len(HELP_SCENARIOS) + 1)

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


if __name__ == "__main__":
    unittest.main()
