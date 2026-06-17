"""Mixin GUI: administración — atajos de promociones."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class AdminShortcutsMixin:
    def configurar_atajos_promociones(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configurar atajos de promociones")
        config_window.geometry("700x360")
        config_window.configure(bg="#ffffff")
        config_window.transient(self.root)
        self._set_modal_grab(config_window)

        tk.Label(
            config_window,
            text="Modo juego: elegí promo y presioná una tecla para bindearla.",
            bg="#ffffff",
            fg="#7F8C8D",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=16, pady=(14, 10))
        tk.Label(
            config_window,
            text="Tip: podés asignar varias teclas por promo. No se permiten conflictos.",
            bg="#ffffff",
            fg="#7F8C8D",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=16, pady=(0, 8))

        estado_captura = tk.Label(
            config_window,
            text="Esperando acción...",
            bg="#ffffff",
            fg="#34495E",
            font=("Segoe UI", 10, "bold"),
        )
        estado_captura.pack(anchor="w", padx=16, pady=(0, 8))
        ultima_tecla_lbl = tk.Label(
            config_window,
            text="Última tecla capturada: -",
            bg="#EAF2F8",
            fg="#1F618D",
            font=("Segoe UI", 14, "bold"),
            padx=12,
            pady=8,
            relief="solid",
            bd=1,
        )
        ultima_tecla_lbl.pack(fill="x", padx=16, pady=(0, 10))

        blocked_keys = {"<Left>", "<Right>", "<KP_Left>", "<KP_Right>", "<Up>", "<Down>", "<KP_Up>", "<KP_Down>"}
        current_hotkeys = self._normalizar_atajos_promociones(self.atajos_promociones)
        rows = {}
        capturando_para = {"promo": None}

        def persistir_atajos_en_vivo():
            normalized_live = self._normalizar_atajos_promociones(current_hotkeys)
            self.atajos_promociones = normalized_live
            self.aplicar_atajos_promos_root()
            for entry in self._entries_operativos:
                self.aplicar_atajos_promos_entry(entry)
            self._save_shortcuts_to_file()
            # Persistimos también en config para mantener compatibilidad.
            self.guardar_configuracion(inmediato=True)

        def refresh_row(promo):
            keys = current_hotkeys.get(promo, [])
            listbox = rows[promo]["listbox"]
            listbox.delete(0, tk.END)
            if not keys:
                listbox.insert(tk.END, "(sin atajos)")
            else:
                for key in keys:
                    listbox.insert(tk.END, key)

        def iniciar_captura(promo):
            capturando_para["promo"] = promo
            estado_captura.config(text=f"Presioná una tecla para {promo}...", fg="#1F618D")

        def limpiar_promo(promo):
            current_hotkeys[promo] = []
            refresh_row(promo)
            persistir_atajos_en_vivo()
            estado_captura.config(text=f"Atajos de {promo} limpiados.", fg="#7F8C8D")

        def agregar_default(promo):
            current_hotkeys[promo] = list(DEFAULT_PROMO_HOTKEYS[promo])
            refresh_row(promo)
            persistir_atajos_en_vivo()
            estado_captura.config(text=f"Atajos por defecto cargados en {promo}.", fg="#7F8C8D")

        def quitar_tecla_seleccionada(promo):
            listbox = rows[promo]["listbox"]
            selection = listbox.curselection()
            if not selection:
                estado_captura.config(text=f"Seleccioná una tecla de {promo} para quitar.", fg="#7F8C8D")
                return
            key_value = listbox.get(selection[0])
            if key_value == "(sin atajos)":
                return
            current_hotkeys[promo] = [key for key in current_hotkeys.get(promo, []) if key != key_value]
            refresh_row(promo)
            persistir_atajos_en_vivo()
            estado_captura.config(text=f"Tecla {key_value} quitada de {promo}.", fg="#7F8C8D")

        def on_keypress_capture(event):
            promo = capturando_para.get("promo")
            if not promo:
                return
            key_token = self._evento_a_tecla_bind(event)
            if not key_token:
                return "break"
            if key_token in blocked_keys:
                estado_captura.config(text=f"La tecla {key_token} está reservada para navegación.", fg="#C0392B")
                capturando_para["promo"] = None
                return "break"

            for other_promo, keys in current_hotkeys.items():
                if other_promo != promo and key_token in keys:
                    estado_captura.config(
                        text=f"Conflicto: {key_token} ya está en {other_promo}.",
                        fg="#C0392B",
                    )
                    capturando_para["promo"] = None
                    return "break"

            if key_token not in current_hotkeys[promo]:
                current_hotkeys[promo].append(key_token)
            refresh_row(promo)
            persistir_atajos_en_vivo()
            estado_captura.config(text=f"{key_token} agregado a {promo}.", fg="#1E8449")
            ultima_tecla_lbl.config(text=f"Última tecla capturada: {key_token}")
            capturando_para["promo"] = None
            return "break"

        config_window.bind("<KeyPress>", on_keypress_capture)
        config_window.focus_force()

        for promo in ["Promo 1", "Promo 2", "Promo 3"]:
            row = tk.Frame(config_window, bg="#ffffff")
            row.pack(fill="x", padx=16, pady=7)
            tk.Label(row, text=f"{promo}", width=10, anchor="w", bg="#ffffff", font=("Segoe UI", 10, "bold")).pack(side="left")

            listbox = tk.Listbox(row, height=3, font=("Segoe UI", 9), exportselection=False)
            listbox.pack(side="left", fill="x", expand=True, padx=(0, 8))

            tk.Button(
                row,
                text="Capturar tecla",
                command=lambda p=promo: iniciar_captura(p),
                bg="#3498DB",
                fg="white",
                font=("Segoe UI", 9, "bold"),
                bd=0,
                padx=8,
                pady=4,
                cursor="hand2",
            ).pack(side="left", padx=(0, 6))
            tk.Button(
                row,
                text="Quitar seleccionada",
                command=lambda p=promo: quitar_tecla_seleccionada(p),
                bg="#E67E22",
                fg="white",
                font=("Segoe UI", 9, "bold"),
                bd=0,
                padx=8,
                pady=4,
                cursor="hand2",
            ).pack(side="left", padx=(0, 6))
            tk.Button(
                row,
                text="Limpiar todo",
                command=lambda p=promo: limpiar_promo(p),
                bg="#AF601A",
                fg="white",
                font=("Segoe UI", 9, "bold"),
                bd=0,
                padx=8,
                pady=4,
                cursor="hand2",
            ).pack(side="left", padx=(0, 6))
            tk.Button(
                row,
                text="Default",
                command=lambda p=promo: agregar_default(p),
                bg="#7F8C8D",
                fg="white",
                font=("Segoe UI", 9, "bold"),
                bd=0,
                padx=8,
                pady=4,
                cursor="hand2",
            ).pack(side="left")
            rows[promo] = {"listbox": listbox}
            refresh_row(promo)

        def guardar_atajos():
            seen = {}
            normalized = self._normalizar_atajos_promociones(current_hotkeys)
            for promo, keys in normalized.items():
                for key in keys:
                    owner = seen.get(key)
                    if owner and owner != promo:
                        messagebox.showerror(
                            "Conflicto de atajos",
                            f"La tecla '{key}' está asignada a {owner} y {promo}.",
                        )
                        return
                    seen[key] = promo

            self.atajos_promociones = normalized
            self.aplicar_atajos_promos_root()
            for entry in self._entries_operativos:
                self.aplicar_atajos_promos_entry(entry)
            self._save_shortcuts_to_file()
            self.guardar_configuracion(inmediato=True)
            config_window.destroy()
            messagebox.showinfo("Atajos", "Atajos de promociones guardados correctamente.")

        botones = tk.Frame(config_window, bg="#ffffff")
        botones.pack(fill="x", padx=16, pady=14)
        tk.Button(botones, text="Guardar", command=guardar_atajos, bg="#4CAF50", fg="white", font=("Arial", 11), bd=0).pack(side="left", padx=(0, 8))
        tk.Button(botones, text="Cancelar", command=config_window.destroy, bg="#D32F2F", fg="white", font=("Arial", 11), bd=0).pack(side="left")
