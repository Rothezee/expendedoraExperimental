import tkinter as tk
from tkinter import messagebox
from .database import add_user

class RegisterWindow:
    def __init__(self, master):
        self.window = tk.Toplevel(master)
        self.window.title("Registro")
        self.window.geometry("400x400")
        self.window.configure(bg="#e9ecef")

        # Título
        self.title_label = tk.Label(self.window, text="Crear Cuenta", bg="#e9ecef", fg="#343a40", font=("Arial", 16, "bold"))
        self.title_label.pack(pady=20)

        # Usuario
        self.username_label = tk.Label(self.window, text="Usuario", bg="#e9ecef", fg="#495057", font=("Arial", 12))
        self.username_label.pack(pady=5)
        self.username_entry = tk.Entry(self.window, font=("Arial", 12), bd=2, relief="flat", bg="#ffffff")
        self.username_entry.pack(pady=5, padx=20, fill='x')
        self.username_entry.bind('<Return>', lambda event: self.password_entry.focus_set())

        # Contraseña
        self.password_label = tk.Label(self.window, text="Contraseña", bg="#e9ecef", fg="#495057", font=("Arial", 12))
        self.password_label.pack(pady=5)
        self.password_entry = tk.Entry(self.window, show="*", font=("Arial", 12), bd=2, relief="flat", bg="#ffffff")
        self.password_entry.pack(pady=5, padx=20, fill='x')
        self.password_entry.bind('<Return>', lambda event: self.register())

        # Botón de Registro
        self.register_button = tk.Button(self.window, text="Registrar", command=self.register, bg="#007BFF", fg="white", font=("Arial", 12, "bold"), bd=0, padx=10, pady=5)
        self.register_button.pack(pady=20)

        # Mensaje de advertencia
        self.warning_label = tk.Label(self.window, text="", bg="#e9ecef", fg="#dc3545", font=("Arial", 10))
        self.warning_label.pack(pady=5)

    def register(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password:
            self.warning_label.config(text="Por favor, complete todos los campos")
            return

        if add_user(username, password):
            messagebox.showinfo("Registro", "Registro exitoso")
            self.window.destroy()
        else:
            self.warning_label.config(text="El usuario ya existe")

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    app = RegisterWindow(root)
    root.mainloop()
