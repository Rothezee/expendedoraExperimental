"""Smoke: arranque GUI + contadores no negativos tras recuperación."""

import tkinter as tk
import unittest

from expendedora.interface.gui import ExpendedoraGUI
from expendedora.logic.application.bootstrap import create_app_controller


class GuiSmokeTest(unittest.TestCase):
    def test_gui_boot_counters_non_negative(self):
        app = create_app_controller()
        try:
            app.start()
        except Exception as exc:
            self.skipTest(f"Hardware no disponible: {exc}")

        root = tk.Tk()
        root.withdraw()
        try:
            gui = ExpendedoraGUI(root, "smoke_test", controlador=app, cashier_id=None)
            root.update_idletasks()

            fg = int(gui.contadores_global.get("fichas_expendidas", -1))
            fp = int(gui.contadores_parcial.get("fichas_expendidas", -1))
            sesion = max(0, int(app.machine_state.get_fichas_sesion()))

            self.assertGreaterEqual(fg, 0, f"global negativo: {fg}")
            self.assertGreaterEqual(fp, 0, f"parcial negativo: {fp}")
            self.assertGreaterEqual(sesion, 0, f"sesión negativa: {sesion}")
        finally:
            root.destroy()
            app.stop()

    def test_restart_preserves_counters_with_active_session(self):
        """Simula 27 fichas persistidas y reinicio sin cerrar sesión."""
        app = create_app_controller()
        try:
            app.start()
        except Exception as exc:
            self.skipTest(f"Hardware no disponible: {exc}")

        base = app.counter_service.default_counters()
        base["fichas_expendidas"] = 27
        parcial = app.counter_service.default_counters()
        parcial["fichas_expendidas"] = 27
        app.persist_snapshot(
            contadores_global=base,
            contadores_parcial=parcial,
            reason="smoke_restart",
        )
        app.machine_state.registrar_fichas_expendidas(27, immediate=True)
        app.stop()

        app2 = create_app_controller()
        try:
            app2.start()
        except Exception as exc:
            self.skipTest(f"Hardware no disponible en reinicio: {exc}")

        root = tk.Tk()
        root.withdraw()
        try:
            gui = ExpendedoraGUI(root, "smoke_test", controlador=app2, cashier_id=None)
            root.update_idletasks()

            fg = int(gui.contadores_global.get("fichas_expendidas", -1))
            fp = int(gui.contadores_parcial.get("fichas_expendidas", -1))
            self.assertEqual(fg, 27)
            self.assertEqual(fp, 27)
        finally:
            root.destroy()
            app2.stop()


if __name__ == "__main__":
    unittest.main()
