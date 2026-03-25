#main.py
import tkinter as tk
from expendedora_gui import ExpendedoraGUI
from expendedora_core import CoreController
from User_management import UserManagement

def main(username):
    core_controller = CoreController()

    # Inicializar el sistema de control del motor
    core_controller.start()

    # Iniciar la interfaz gráfica
    root = tk.Tk()
    app = ExpendedoraGUI(root, username, core_controller=core_controller)
    root.mainloop()

    # Detener el sistema al cerrar
    core_controller.stop()

if __name__ == "__main__":
    user_management = UserManagement(main_callback=main)
    user_management.run()