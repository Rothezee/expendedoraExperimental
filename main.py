#main.py
import tkinter as tk
from expendedora_gui import ExpendedoraGUI
from expendedora_core import CoreController
from User_management import UserManagement


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
    core_controller = CoreController()
    logout_requested = {"value": False}
    action = "exit"
    core_started = False

    # Inicializar el sistema de control del motor
    try:
        core_controller.start()
        core_started = True
        _trace("core_controller.start() OK")
    except Exception as exc:
        # No abortar UI por fallas de bridge al arrancar.
        _trace(f"Aviso al iniciar core: {type(exc).__name__}: {exc}")

    try:
        # Iniciar la interfaz gráfica
        root = tk.Tk()
        _trace("Tk root principal creado")
        app = ExpendedoraGUI(
            root,
            username,
            core_controller=core_controller,
            cashier_id=cashier_id,
            on_logout=lambda: logout_requested.update({"value": True}),
        )
        _trace("ExpendedoraGUI inicializada; entrando a mainloop")
        root.mainloop()
        action = "logout" if logout_requested["value"] else "exit"
        _trace(f"mainloop finalizado con action={action}")
        return action
    finally:
        # Detener el sistema al cerrar (best-effort para no matar el loop login->app).
        if core_started:
            try:
                core_controller.stop()
            except Exception as exc:
                _trace(f"Aviso al detener core: {type(exc).__name__}: {exc}")
        _trace("main() end")


def run_kiosk_loop():
    """
    Orquesta login -> app principal evitando árboles Tk anidados.
    """
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