"""Mixin GUI: administración — ajustes máquina."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class AdminSettingsMixin:
    def configurar_promo(self, promo):
        config_window = tk.Toplevel(self.root)
        config_window.title(f"Configurar {promo}")
        config_window.geometry("300x250")
        config_window.configure(bg="#ffffff")
        config_window.transient(self.root)
        self._set_modal_grab(config_window)

        promo_cfg = self.promociones.get(promo)
        if not isinstance(promo_cfg, dict):
            promo_cfg = {"precio": 0, "fichas": 0}
            self.promociones[promo] = promo_cfg

        tk.Label(config_window, text="Precio (en $):", bg="#ffffff", font=("Arial", 12)).pack(pady=10)
        precio_entry = tk.Entry(config_window, font=("Arial", 12), bd=2, relief="solid")
        precio_entry.insert(0, promo_cfg.get("precio", 0))
        precio_entry.pack(pady=5, padx=10, fill='x')
        
        tk.Label(config_window, text="Fichas entregadas:", bg="#ffffff", font=("Arial", 12)).pack(pady=10)
        fichas_entry = tk.Entry(config_window, font=("Arial", 12), bd=2, relief="solid")
        fichas_entry.insert(0, promo_cfg.get("fichas", 0))
        fichas_entry.pack(pady=5, padx=10, fill='x')
        
        def guardar_promo():
            try:
                self.promociones[promo]["precio"] = float(precio_entry.get())
                self.promociones[promo]["fichas"] = int(fichas_entry.get())
                self.guardar_configuracion(inmediato=True)
                config_window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Ingrese valores numéricos válidos.")
        
        tk.Button(config_window, text="Guardar", command=guardar_promo, bg="#4CAF50", fg="white", font=("Arial", 12), bd=0).pack(pady=5)
        tk.Button(config_window, text="Cancelar", command=config_window.destroy, bg="#D32F2F", fg="white", font=("Arial", 12), bd=0).pack(pady=5)


    def configurar_valor_ficha(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configurar Valor de Ficha")
        config_window.geometry("300x150")
        config_window.configure(bg="#ffffff")
        
        tk.Label(config_window, text="Valor de cada ficha (en $):", bg="#ffffff", font=("Arial", 12)).pack(pady=10)
        valor_entry = tk.Entry(config_window, font=("Arial", 12), bd=2, relief="solid")
        valor_entry.insert(0, self.valor_ficha)
        valor_entry.pack(pady=5, padx=10, fill='x')
        
        def guardar_valor_ficha():
            try:
                self.valor_ficha = float(valor_entry.get())
                self.guardar_configuracion(inmediato=True)
                config_window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Ingrese un valor numérico válido.")
        
        tk.Button(config_window, text="Guardar", command=guardar_valor_ficha, bg="#4CAF50", fg="white", font=("Arial", 12), bd=0).pack(pady=5)
        tk.Button(config_window, text="Cancelar", command=config_window.destroy, bg="#D32F2F", fg="white", font=("Arial", 12), bd=0).pack(pady=5)


    def configurar_device_id(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configurar Codigo Hardware")
        config_window.geometry("300x150")
        config_window.configure(bg="#ffffff")
        
        tk.Label(config_window, text="Codigo de Hardware:", bg="#ffffff", font=("Arial", 12)).pack(pady=10)
        id_entry = tk.Entry(config_window, font=("Arial", 12), bd=2, relief="solid")
        id_entry.insert(0, self.codigo_hardware or self.device_id)
        id_entry.pack(pady=5, padx=10, fill='x')
        
        def guardar_id():
            new_id = id_entry.get().strip()
            if new_id:
                self.codigo_hardware = new_id
                self.device_id = new_id  # Alias legacy
                self.guardar_configuracion(inmediato=True)
                config_window.destroy()
            else:
                messagebox.showerror("Error", "El ID no puede estar vacío.")
        
        tk.Button(config_window, text="Guardar", command=guardar_id, bg="#4CAF50", fg="white", font=("Arial", 12), bd=0).pack(pady=5)
        tk.Button(config_window, text="Cancelar", command=config_window.destroy, bg="#D32F2F", fg="white", font=("Arial", 12), bd=0).pack(pady=5)


    def configurar_dni_admin(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configurar DNI Admin")
        config_window.geometry("300x150")
        config_window.configure(bg="#ffffff")

        tk.Label(config_window, text="DNI Administrador:", bg="#ffffff", font=("Arial", 12)).pack(pady=10)
        dni_entry = tk.Entry(config_window, font=("Arial", 12), bd=2, relief="solid")
        dni_entry.insert(0, self.dni_admin)
        dni_entry.pack(pady=5, padx=10, fill='x')

        def guardar_dni():
            nuevo_dni = dni_entry.get().strip()
            if nuevo_dni:
                self.dni_admin = nuevo_dni
                self.guardar_configuracion(inmediato=True)
                config_window.destroy()
            else:
                messagebox.showerror("Error", "El DNI no puede estar vacío.")

        tk.Button(config_window, text="Guardar", command=guardar_dni, bg="#4CAF50", fg="white", font=("Arial", 12), bd=0).pack(pady=5)
        tk.Button(config_window, text="Cancelar", command=config_window.destroy, bg="#D32F2F", fg="white", font=("Arial", 12), bd=0).pack(pady=5)

