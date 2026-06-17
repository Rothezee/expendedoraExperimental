"""Mixin GUI: administración — calibración y red."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class AdminHardwareMixin:
    def configurar_calibracion_tolvas(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Calibrar sensores de tolvas")
        config_window.geometry("760x460")
        config_window.configure(bg="#ffffff")

        tk.Label(
            config_window,
            text="Guía: 1) Seleccioná tolva  2) Simulá/pasá ficha  3) Ajustá umbrales  4) Guardá y probá",
            bg="#ffffff",
            fg="#7F8C8D",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=16, pady=(14, 10))

        body = tk.Frame(config_window, bg="#ffffff")
        body.pack(fill="both", expand=True, padx=16, pady=4)

        entries = {}
        hoppers = self._hoppers_configurados()
        if not hoppers:
            tk.Label(body, text="No hay tolvas en config.json (maquina.hoppers).", bg="#ffffff", fg="#7F8C8D").pack(pady=20)
        for idx, hopper in enumerate(hoppers):
            card = tk.Frame(body, bg="#F8F9F9", bd=1, relief="solid")
            card.pack(fill="x", pady=6)
            tk.Label(
                card,
                text=f"{hopper.get('nombre', f'Tolva {idx+1}')} (sensor pin {hopper.get('sensor_pin', '-')})",
                bg="#F8F9F9",
                fg="#2C3E50",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", padx=12, pady=(8, 6))

            calib = hopper.get("calibracion", {}) if isinstance(hopper.get("calibracion", {}), dict) else {}
            pulso_min_ms = float(calib.get("pulso_min_s", 0.05)) * 1000.0
            pulso_max_ms = float(calib.get("pulso_max_s", 0.5)) * 1000.0
            timeout_s = float(calib.get("timeout_motor_s", 2.0))

            row = tk.Frame(card, bg="#F8F9F9")
            row.pack(fill="x", padx=12, pady=(0, 10))

            tk.Label(row, text="Pulso mínimo (ms)", bg="#F8F9F9", font=("Segoe UI", 9)).pack(side="left")
            min_entry = tk.Entry(row, width=8, font=("Segoe UI", 9), justify="center")
            min_entry.insert(0, f"{pulso_min_ms:.1f}")
            min_entry.pack(side="left", padx=(6, 14))

            tk.Label(row, text="Pulso máximo (ms)", bg="#F8F9F9", font=("Segoe UI", 9)).pack(side="left")
            max_entry = tk.Entry(row, width=8, font=("Segoe UI", 9), justify="center")
            max_entry.insert(0, f"{pulso_max_ms:.1f}")
            max_entry.pack(side="left", padx=(6, 14))

            tk.Label(row, text="Timeout motor (s)", bg="#F8F9F9", font=("Segoe UI", 9)).pack(side="left")
            timeout_entry = tk.Entry(row, width=8, font=("Segoe UI", 9), justify="center")
            timeout_entry.insert(0, f"{timeout_s:.2f}")
            timeout_entry.pack(side="left", padx=(6, 14))

            entries[idx] = (min_entry, max_entry, timeout_entry)

        def guardar_calibracion():
            try:
                for idx, triplet in entries.items():
                    min_entry, max_entry, timeout_entry = triplet
                    pulso_min_ms = float(min_entry.get())
                    pulso_max_ms = float(max_entry.get())
                    timeout_motor_s = float(timeout_entry.get())

                    if pulso_min_ms <= 0 or pulso_max_ms <= 0 or timeout_motor_s <= 0:
                        raise ValueError("Los valores deben ser positivos.")
                    if pulso_max_ms < pulso_min_ms:
                        raise ValueError("Pulso máximo no puede ser menor a pulso mínimo.")

                    if idx < 0 or idx >= len(hoppers):
                        continue
                    hopper = hoppers[idx]
                    calibracion = hopper.get("calibracion", {})
                    if not isinstance(calibracion, dict):
                        calibracion = {}
                    calibracion["pulso_min_s"] = pulso_min_ms / 1000.0
                    calibracion["pulso_max_s"] = pulso_max_ms / 1000.0
                    calibracion["timeout_motor_s"] = timeout_motor_s
                    hopper["calibracion"] = calibracion

                self.guardar_configuracion(inmediato=True)
                # Permite aplicar nueva calibración sin reiniciar la app.
                try:
                    self.app.recargar_tolvas_desde_config()
                except Exception as exc:
                    print(f"[GUI] No se pudo recargar calibración en caliente: {exc}")
                config_window.destroy()
                messagebox.showinfo("Calibración", "Calibración de tolvas guardada correctamente.")
            except ValueError as exc:
                messagebox.showerror("Error", str(exc))

        botones = tk.Frame(config_window, bg="#ffffff")
        botones.pack(fill="x", padx=16, pady=14)
        tk.Button(botones, text="Guardar", command=guardar_calibracion, bg="#4CAF50", fg="white", font=("Arial", 11), bd=0).pack(side="left", padx=(0, 8))
        tk.Button(botones, text="Cancelar", command=config_window.destroy, bg="#D32F2F", fg="white", font=("Arial", 11), bd=0).pack(side="left")


    def configurar_gestor_red(self):
        is_admin = self._is_admin_user()
        config_window = tk.Toplevel(self.root)
        config_window.title("Configurar gestor de red")
        config_window.geometry("560x560")
        config_window.minsize(560, 560)
        config_window.configure(bg="#ffffff")
        config_window.transient(self.root)
        self._set_modal_grab(config_window)

        cfg = dict(self.network_manager_cfg) if isinstance(self.network_manager_cfg, dict) else {}

        enabled_var = tk.BooleanVar(value=bool(cfg.get("enabled", True)))
        check_interval_var = tk.StringVar(value=str(cfg.get("check_interval_s", 8)))
        retry_var = tk.StringVar(value=str(cfg.get("reconnect_after_failures", 3)))
        timeout_var = tk.StringVar(value=str(cfg.get("backend_timeout_s", 3.0)))
        internet_host_var = tk.StringVar(value=str(cfg.get("internet_host", "8.8.8.8")))
        backend_url_var = tk.StringVar(value=str(cfg.get("backend_url", self._build_backend_probe_url())))
        iface_var = tk.StringVar(value=str(cfg.get("preferred_interface", "")))
        wifi_ssid_var = tk.StringVar(value=str(cfg.get("wifi_ssid", "")))
        wifi_password_var = tk.StringVar(value=str(cfg.get("wifi_password", "")))

        content_frame = tk.Frame(config_window, bg="#ffffff")
        content_frame.pack(fill="both", expand=True, padx=16, pady=(14, 8))

        tk.Label(
            content_frame,
            text=(
                "Monitor en tiempo real + reconexión automática (Linux: nmcli, Windows: netsh)."
                if is_admin
                else "Modo usuario: solo conexión Wi-Fi segura. Configuración avanzada bloqueada."
            ),
            bg="#ffffff",
            fg="#7F8C8D",
            font=("Segoe UI", 10),
            justify="left",
        ).pack(anchor="w", pady=(0, 10))
        if is_admin:
            tk.Checkbutton(
                content_frame,
                text="Habilitar gestor de red",
                variable=enabled_var,
                bg="#ffffff",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(0, 10))
        else:
            tk.Label(
                content_frame,
                text="Los parámetros de monitor/reconexión se gestionan por administrador.",
                bg="#ffffff",
                fg="#A04000",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w", pady=(0, 10))

        form = tk.Frame(content_frame, bg="#ffffff")
        form.pack(fill="x", pady=(0, 8))

        def add_row(label, variable, show=None):
            row = tk.Frame(form, bg="#ffffff")
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, width=26, anchor="w", bg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
            entry_kwargs = {"textvariable": variable, "font": ("Segoe UI", 9), "justify": "left"}
            if show is not None:
                entry_kwargs["show"] = show
            tk.Entry(row, **entry_kwargs).pack(side="left", fill="x", expand=True)

        if is_admin:
            add_row("Intervalo de chequeo (s)", check_interval_var)
            add_row("Fallas antes de reconectar", retry_var)
            add_row("Timeout backend (s)", timeout_var)
            add_row("Host de prueba internet", internet_host_var)
            add_row("URL backend para healthcheck", backend_url_var)
            add_row("Interfaz preferida (ej: wlan0)", iface_var)
        ssid_row = tk.Frame(form, bg="#ffffff")
        ssid_row.pack(fill="x", pady=5)
        tk.Label(ssid_row, text="Wi-Fi SSID", width=26, anchor="w", bg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        ssid_combo = ttk.Combobox(
            ssid_row,
            textvariable=wifi_ssid_var,
            font=("Segoe UI", 9),
            state="normal",
        )
        ssid_combo.pack(side="left", fill="x", expand=True)
        tk.Button(
            ssid_row,
            text="Refrescar",
            bg="#5D6D7E",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            bd=0,
            padx=8,
            command=lambda: refresh_ssid_options(),
        ).pack(side="left", padx=(6, 0))
        add_row("Wi-Fi contraseña", wifi_password_var, show="*")

        def refresh_ssid_options():
            options = self.network_service.list_wifi_networks()
            if not options:
                return
            ssid_combo["values"] = options
            current = wifi_ssid_var.get().strip()
            if not current:
                wifi_ssid_var.set(options[0])

        refresh_ssid_options()

        tk.Label(
            content_frame,
            text=(
                "Tip: podés seleccionar una red detectada o escribir un SSID manualmente."
                if is_admin
                else "Solo se permite cambiar SSID y contraseña Wi-Fi en modo usuario."
            ),
            bg="#ffffff",
            fg="#7F8C8D",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        def guardar():
            try:
                if is_admin:
                    new_cfg = {
                        "enabled": bool(enabled_var.get()),
                        "check_interval_s": max(2, int(float(check_interval_var.get()))),
                        "reconnect_after_failures": max(1, int(float(retry_var.get()))),
                        "backend_timeout_s": max(0.5, float(timeout_var.get())),
                        "internet_host": internet_host_var.get().strip() or "8.8.8.8",
                        "backend_url": backend_url_var.get().strip(),
                        "preferred_interface": iface_var.get().strip(),
                        "wifi_ssid": wifi_ssid_var.get().strip(),
                        "wifi_password": wifi_password_var.get(),
                    }
                else:
                    # Usuario común: solo puede actualizar credenciales Wi-Fi.
                    new_cfg = dict(cfg)
                    new_cfg["wifi_ssid"] = wifi_ssid_var.get().strip()
                    new_cfg["wifi_password"] = wifi_password_var.get()
            except ValueError:
                messagebox.showerror("Error", "Revisá los valores numéricos del gestor de red.")
                return

            self.network_manager_cfg = new_cfg
            self.guardar_configuracion(inmediato=True)
            self.network_service.stop()
            self.network_service.start(callback=self._on_network_status_changed)
            wifi_result = ""
            if new_cfg["wifi_ssid"]:
                ok, detail = self.network_service.connect_configured_network()
                if ok:
                    wifi_result = "\nConexión Wi-Fi aplicada con la red configurada."
                else:
                    wifi_result = f"\nNo se pudo aplicar la red Wi-Fi ahora: {detail}"
            config_window.destroy()
            messagebox.showinfo("Gestor de red", f"Configuración guardada y monitor reiniciado.{wifi_result}")

        btn_row = tk.Frame(config_window, bg="#ffffff")
        btn_row.pack(side="bottom", fill="x", padx=16, pady=(6, 12))

        def conectar_ahora():
            ok, detail = self.network_service.connect_configured_network()
            if ok:
                messagebox.showinfo("Gestor de red", "Conexión iniciada.")
            else:
                messagebox.showwarning("Gestor de red", f"No se pudo conectar: {detail}")

        tk.Button(
            btn_row,
            text="Conectar ahora",
            command=conectar_ahora,
            bg="#2980B9",
            fg="white",
            font=("Arial", 11, "bold"),
            activebackground="#1F618D",
            activeforeground="white",
            bd=0,
            width=14,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            btn_row,
            text="Guardar",
            command=guardar,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 11, "bold"),
            activebackground="#3D8B40",
            activeforeground="white",
            bd=0,
            width=12,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            btn_row,
            text="Cancelar",
            command=config_window.destroy,
            bg="#D32F2F",
            fg="white",
            font=("Arial", 11, "bold"),
            activebackground="#A4281F",
            activeforeground="white",
            bd=0,
            width=12,
        ).pack(side="left")
