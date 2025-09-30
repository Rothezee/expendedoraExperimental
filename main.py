#main.py
import threading
import tkinter as tk
from expendedora_gui import ExpendedoraGUI
from expendedora_core import enviar_pulso, init_db
from User_management import UserManagement

def start_gui():
    root = tk.Tk()
    app = ExpendedoraGUI(root, username="username") 
    root.mainloop()
    
def main(username):
    # Inicializar la base de datos
    init_db()
    
    # Iniciar el envío de pulsos al servidor
    threading.Thread(target=enviar_pulso).start()
    
    # Iniciar la interfaz gráfica
    root = tk.Tk()
    app = ExpendedoraGUI(root, username)  # Pasar el nombre de usuario
    root.mainloop()

if __name__ == "__main__":
    user_management = UserManagement(main_callback=main)  # Pasar la función main como callback
    user_management.run()  # No se pasa ningún argumento aquí