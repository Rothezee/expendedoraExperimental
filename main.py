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

    # Inicializar el sistema de control del motor
    core_controller.start()

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

    # Detener el sistema al cerrar
    core_controller.stop()
    return "logout" if logout_requested["value"] else "exit"


def run_kiosk_loop():
    """
    Orquesta login -> app principal evitando árboles Tk anidados.
    """
    while True:
        user_management = UserManagement(main_callback=None)
        user_session = user_management.run()
        if not user_session:
            break
        action = main(user_session)
        if action != "logout":
            break

if __name__ == "__main__":
    run_kiosk_loop()