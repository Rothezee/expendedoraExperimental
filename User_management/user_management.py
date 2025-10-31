import tkinter as tk
from .login import LoginWindow
from .register import RegisterWindow
from .database import create_table

class UserManagement:
    def __init__(self, main_callback):
        self.main_callback = main_callback  # Guardar el callback
        create_table()  # Crear la tabla de usuarios si no existe
        self.root = tk.Tk()
        self.root.title("Sistema de Control de Usuarios") # El título no será visible
        self.root.attributes('-fullscreen', True) # Ocupa 100% de pantalla y oculta la barra de título
        self.root.configure(bg="#e9ecef")

        self.main_frame = tk.Frame(self.root, bg="#e9ecef")
        self.main_frame.pack(pady=50)

        # Título
        self.title_label = tk.Label(self.main_frame, text="Gestión de Usuarios", bg="#e9ecef", fg="#343a40", font=("Arial", 16, "bold"))
        self.title_label.pack(pady=20)

        # Botón de Login
        self.login_button = tk.Button(self.main_frame, text="Iniciar Sesión", command=self.open_login, bg="#007BFF", fg="white", font=("Arial", 12, "bold"), bd=0, padx=10, pady=5)
        self.login_button.pack(pady=10)

        # Botón de Register
        self.register_button = tk.Button(self.main_frame, text="Registrar", command=self.open_register, bg="#007BFF", fg="white", font=("Arial", 12, "bold"), bd=0, padx=10, pady=5)
        self.register_button.pack(pady=10)

    def open_login(self):
        LoginWindow(self.root, self.on_login_success)  # Pasar la función de éxito

    def open_register(self):
        RegisterWindow(self.root)

    def on_login_success(self, username):
        self.root.destroy()  # Cerrar la ventana de gestión de usuarios
        self.main_callback(username)  # Pasar el nombre de usuario a main

    def run(self):
        self.root.mainloop()