"""Punto de entrada del kiosko (capa interfaz)."""

import getpass
import os
import sys
from pathlib import Path

# Permite `python expendedora/interface/main.py` o depurar ese archivo directo.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from expendedora.interface.auth import UserManagement
from expendedora.interface.gui import ExpendedoraGUI
from expendedora.interface.kiosk_env import kiosk_mode_habilitado
from expendedora.logic.application.bootstrap import create_app_controller


def _trace(msg: str) -> None:
    print(f"[MAIN] {msg}")


def _parse_user_session(user_session):
    if isinstance(user_session, dict):
        username = str(user_session.get("username", "")).strip() or "admin"
        cashier_id = user_session.get("cashier_id")
        try:
            cashier_id = int(cashier_id) if cashier_id is not None else None
        except (TypeError, ValueError):
            cashier_id = None
        return username, cashier_id
    return str(user_session), None


def main(user_session):
    username, cashier_id = _parse_user_session(user_session)
    _trace(f"main() start user={username!r} cashier_id={cashier_id}")
    app = create_app_controller()
    logout_requested = {"value": False}
    action = "exit"
    core_started = False

    try:
        app.start()
        core_started = True
        _trace("app.start() OK")
    except Exception as exc:
        _trace(f"Aviso al iniciar app: {type(exc).__name__}: {exc}")

    try:
        import tkinter as tk

        root = tk.Tk()
        _trace("Tk root principal creado")
        ExpendedoraGUI(
            root,
            username,
            controlador=app,
            cashier_id=cashier_id,
            on_logout=lambda: logout_requested.update({"value": True}),
        )
        _trace("ExpendedoraGUI inicializada; entrando a mainloop")
        root.mainloop()
        action = "logout" if logout_requested["value"] else "exit"
        _trace(f"mainloop finalizado con action={action}")
        return action
    finally:
        if core_started:
            try:
                app.stop()
            except Exception as exc:
                _trace(f"Aviso al detener app: {type(exc).__name__}: {exc}")
        _trace("main() end")


def _kiosk_session_user() -> str:
    explicit = str(os.environ.get("EXPENDEDORA_KIOSK_USER", "")).strip()
    if explicit:
        return explicit
    return str(getpass.getuser() or "cajero").strip() or "cajero"


def run_kiosk_autostart():
    """
    Modo mostrador: sin pantalla de login (usuario Windows = sesión de cajero).
    Activar con EXPENDEDORA_KIOSK=1 (launcher kiosk en Windows).
    """
    username = _kiosk_session_user()
    _trace(f"Kiosk autostart user={username!r}")
    while True:
        try:
            action = main({"username": username, "cashier_id": None})
        except Exception as exc:
            _trace(f"Error en app kiosk: {type(exc).__name__}: {exc}")
            action = "exit"
        if action == "logout":
            _trace("Logout en kiosk; volviendo a abrir app")
            continue
        _trace("Cierre de app kiosk; saliendo")
        break


def run_kiosk_loop():
    """Orquesta login -> app principal evitando árboles Tk anidados."""
    if kiosk_mode_habilitado():
        run_kiosk_autostart()
        return
    while True:
        try:
            _trace("Iniciando UserManagement()")
            user_management = UserManagement(main_callback=None)
            user_session = user_management.run()
            _trace(f"UserManagement.run() retornó: {user_session!r}")
        except Exception as exc:
            _trace(f"Error en manager de usuarios: {type(exc).__name__}: {exc}")
            continue
        if not user_session:
            _trace("Sin sesión de usuario; saliendo loop kiosko")
            break
        try:
            action = main(user_session)
        except Exception as exc:
            _trace(f"Error ejecutando app principal: {type(exc).__name__}: {exc}")
            action = "logout"
        if action != "logout":
            _trace("Acción distinta de logout; cerrando app")
            break


if __name__ == "__main__":
    run_kiosk_loop()
