#main.py
import tkinter as tk
from expendedora_gui import ExpendedoraGUI
import expendedora_core as core
from User_management import UserManagement

def main(username):
    # Inicializar el sistema de control del motor
    core.iniciar_sistema()

    # Iniciar la interfaz gráfica
    root = tk.Tk()
    app = ExpendedoraGUI(root, username)
    root.mainloop()

    # Detener el sistema al cerrar
    core.detener_sistema()

if __name__ == "__main__":
    user_management = UserManagement(main_callback=main)
    user_management.run()