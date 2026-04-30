#main.py
import tkinter as tk
from expendedora_gui import ExpendedoraGUI
from expendedora_core import CoreController
from User_management import UserManagement

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
    core_controller = CoreController()
    logout_requested = {"value": False}
    action = "exit"

    # Inicializar el sistema de control del motor
    core_controller.start()

    try:
        # Iniciar la interfaz gráfica
        root = tk.Tk()
        app = ExpendedoraGUI(
            root,
            username,
            core_controller=core_controller,
            cashier_id=cashier_id,
            on_logout=lambda: logout_requested.update({"value": True}),
        )
        root.mainloop()
        action = "logout" if logout_requested["value"] else "exit"
        return action
    finally:
        # Detener el sistema al cerrar (best-effort para no matar el loop login->app).
        try:
            core_controller.stop()
        except Exception as exc:
            print(f"[MAIN] Aviso al detener core: {type(exc).__name__}: {exc}")


def run_kiosk_loop():
    """
    Orquesta login -> app principal evitando árboles Tk anidados.
    """
    while True:
        try:
            user_management = UserManagement(main_callback=None)
            user_session = user_management.run()
        except Exception as exc:
            print(f"[MAIN] Error en manager de usuarios: {type(exc).__name__}: {exc}")
            continue
        if not user_session:
            break
        try:
            action = main(user_session)
        except Exception as exc:
            print(f"[MAIN] Error ejecutando app principal: {type(exc).__name__}: {exc}")
            action = "logout"
        if action != "logout":
            break

if __name__ == "__main__":
    run_kiosk_loop()