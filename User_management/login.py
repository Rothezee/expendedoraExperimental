import tkinter as tk
from tkinter import messagebox
from .database import get_user

class LoginWindow:
    def __init__(self, master, success_callback):
        self.window = tk.Toplevel(master)
        self.window.title("Iniciar Sesión")
        self.window.geometry("400x300")
        self.window.configure(bg="#e9ecef")
        self.success_callback = success_callback  # Guardar el callback

        # Título
        self.title_label = tk.Label(self.window, text="Iniciar Sesión", bg="#e9ecef", fg="#343a40", font=("Arial", 16, "bold"))
        self.title_label.pack(pady=20)

        # Usuario
        self.user_label = tk.Label(self.window, text="Usuario", bg="#e9ecef", fg="#495057", font=("Arial", 12))
        self.user_label.pack(pady=5)
        self.user_entry = tk.Entry(self.window, font=("Arial", 12), bd=2, relief="flat", bg="#ffffff")
        self.user_entry.pack(pady=5, padx=20, fill='x')
        self.user_entry.bind('<Return>', lambda event: self.password_entry.focus_set())

        # Contraseña
        self.password_label = tk.Label(self.window, text="Contraseña", bg="#e9ecef", fg="#495057", font=("Arial", 12))
        self.password_label.pack(pady=5)
        self.password_entry = tk.Entry(self.window, show="*", font=("Arial", 12), bd=2, relief="flat", bg="#ffffff")
        self.password_entry.pack(pady=5, padx=20, fill='x')
        self.password_entry.bind('<Return>', lambda event: self.login())

        # Botón de Iniciar Sesión
        self.login_button = tk.Button(self.window, text="Iniciar Sesión", command=self.login, bg="#007BFF", fg="white", font=("Arial", 12, "bold"), bd=0, padx=10, pady=5)
        self.login_button.pack(pady=20)

        # Mensaje de advertencia
        self.warning_label = tk.Label(self.window, text="", bg="#e9ecef", fg="#dc3545", font=("Arial", 10))
        self.warning_label.pack(pady=5)

    def login(self):
        usuario = self.user_entry.get()
        password = self.password_entry.get()

        if not usuario or not password:
            self.warning_label.config(text="Por favor, complete todos los campos")
            return

        user = get_user(nombre=usuario, contraceña=password)

        if user:
            messagebox.showinfo("Login", "Login exitoso")
            self.window.destroy()  # Cierra la ventana de login
            self.success_callback(usuario)  # Llama al callback de éxito con el nombre de usuario
        else:
            messagebox.showerror("Login", "Usuario o contraseña incorrectos")
            self.warning_label.config(text="Usuario o contraseña incorrectos")
