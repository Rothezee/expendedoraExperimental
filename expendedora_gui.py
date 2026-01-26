def procesar_expender_fichas(self):
    try:
        cantidad_str = self.entry_fichas.get()
        if not cantidad_str:
            self.entry_fichas.focus_set()
            return
        
        cantidad_fichas = int(cantidad_str)
        if cantidad_fichas <= 0:
            messagebox.showerror("Error", "La cantidad debe ser mayor a 0.")
            self.entry_fichas.focus_set()  # <-- AÑADIR ESTO
            return

        # Actualiza la GUI de forma optimista
        current_fichas = self.contadores["fichas_restantes"]
        self.contadores_labels["fichas_restantes"].config(text=f"Fichas Restantes: {current_fichas + cantidad_fichas}")

        # Enviar comando al core
        shared_buffer.gui_to_core_queue.put({'type': 'add_fichas', 'cantidad': cantidad_fichas})

        # Actualizar contadores
        dinero = cantidad_fichas * self.valor_ficha
        self.contadores["dinero_ingresado"] += dinero
        self.contadores_apertura["dinero_ingresado"] += dinero
        self.contadores_parciales["dinero_ingresado"] += dinero

        self.contadores["fichas_normales"] += cantidad_fichas
        self.contadores_apertura["fichas_normales"] += cantidad_fichas
        self.contadores_parciales["fichas_normales"] += cantidad_fichas

        shared_buffer.set_r_cuenta(self.contadores["dinero_ingresado"])

        self.guardar_configuracion()
        self.contadores_labels["dinero_ingresado"].config(text=f"Dinero Ingresado: ${self.contadores['dinero_ingresado']:.2f}")
        
        # Limpiar el campo de entrada
        self.entry_fichas.delete(0, tk.END)
        
        # **SOLUCIÓN LINUX**: Devolver foco explícitamente al entry
        # Esto mantiene los bindings activos sin necesidad de clic
        self.entry_fichas.focus_set()
        
    except ValueError:
        messagebox.showerror("Error", "Ingrese un valor numérico válido.")
        self.entry_fichas.focus_set()  # <-- AÑADIR ESTO

def procesar_devolucion_fichas(self):
    try:
        cantidad_str = self.entry_devolucion.get()
        if not cantidad_str:
            self.entry_devolucion.focus_set()
            return
        
        cantidad_fichas = int(cantidad_str)
        if cantidad_fichas <= 0:
            messagebox.showerror("Error", "La cantidad debe ser mayor a 0.")
            self.entry_devolucion.focus_set()  # <-- AÑADIR ESTO
            return

        # Actualización optimista
        current_fichas = self.contadores["fichas_restantes"]
        self.contadores_labels["fichas_restantes"].config(text=f"Fichas Restantes: {current_fichas + cantidad_fichas}")

        shared_buffer.gui_to_core_queue.put({'type': 'add_fichas', 'cantidad': cantidad_fichas})

        # Actualizar contadores de devolución
        self.contadores["fichas_devolucion"] += cantidad_fichas
        self.contadores_apertura["fichas_devolucion"] += cantidad_fichas
        self.contadores_parciales["fichas_devolucion"] += cantidad_fichas

        self.guardar_configuracion()
        
        if "fichas_devolucion" in self.contadores_labels:
             self.contadores_labels["fichas_devolucion"].config(text=f"{self.contadores['fichas_devolucion']}")

        self.entry_devolucion.delete(0, tk.END)
        
        # **CAMBIO CRÍTICO**: Mostrar mensaje DESPUÉS de restaurar el foco
        # O mejor aún: usar un label de notificación en vez de messagebox
        self.entry_devolucion.focus_set()
        
        # OPCIONAL: Si necesitas el mensaje, hazlo así:
        # self.root.after(100, lambda: messagebox.showinfo("Devolución", f"Se han agregado {cantidad_fichas} fichas de devolución."))
        
    except ValueError:
        messagebox.showerror("Error", "Ingrese un valor numérico válido.")
        self.entry_devolucion.focus_set()  # <-- AÑADIR ESTO
