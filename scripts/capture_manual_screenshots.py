"""Genera capturas PNG del manual (ejecutar con la app cerrada o en segundo plano)."""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCREENSHOTS_DIR = ROOT / "expendedora" / "interface" / "gui" / "docs" / "screenshots"

CAPTURES: list[tuple[str, str, str]] = [
    ("inicio.png", "main_frame", "Pantalla principal"),
    ("contadores.png", "contadores_page", "Contadores"),
    ("cierre.png", "reportes_frame", "Cierre y reportes"),
]


def _grab_window(root: tk.Tk, dest: Path) -> None:
    root.update_idletasks()
    root.update()
    time.sleep(0.35)
    x1 = root.winfo_rootx()
    y1 = root.winfo_rooty()
    x2 = x1 + root.winfo_width()
    y2 = y1 + root.winfo_height()
    ImageGrab.grab(bbox=(x1, y1, x2, y2)).save(dest, format="PNG")


def main() -> int:
    from expendedora.interface.gui import ExpendedoraGUI
    from expendedora.logic.application.bootstrap import create_app_controller

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    app = create_app_controller()
    try:
        app.start()
    except Exception as exc:
        print(f"[CAPTURE] Aviso hardware: {exc}")

    root = tk.Tk()
    root.title("Expendedora — captura manual")
    gui = ExpendedoraGUI(root, "admin", controlador=app, cashier_id=None)

    try:
        root.attributes("-fullscreen", False)
    except tk.TclError:
        pass
    root.geometry("1280x800")
    root.minsize(1024, 700)
    root.update_idletasks()

    frames = {
        "main_frame": gui.main_frame,
        "contadores_page": gui.contadores_page,
        "reportes_frame": gui.reportes_frame,
    }

    for filename, frame_key, label in CAPTURES:
        frame = frames.get(frame_key)
        if frame is None:
            print(f"[CAPTURE] Omitido {filename}: frame {frame_key!r} no existe")
            continue
        gui.mostrar_frame(frame)
        dest = SCREENSHOTS_DIR / filename
        _grab_window(root, dest)
        print(f"[CAPTURE] {label} -> {dest}")

    root.destroy()
    app.stop()
    print(f"[CAPTURE] Listo ({len(CAPTURES)} archivos en {SCREENSHOTS_DIR})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
