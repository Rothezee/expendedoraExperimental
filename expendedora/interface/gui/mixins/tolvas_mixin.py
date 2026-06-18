"""Mixin GUI: tolvas y motor."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class TolvasMixin:
    def seleccionar_tolva_siguiente(self):
        self.app.seleccionar_tolva_siguiente()
        self.actualizar_tolvas_gui()


    def seleccionar_tolva_anterior(self):
        self.app.seleccionar_tolva_anterior()
        self.actualizar_tolvas_gui()


    def _estados_tolvas_fallback(self):
        """Estados desde config cuando el core aún no publicó tolvas."""
        hoppers_cfg = self._hoppers_configurados()
        if not hoppers_cfg:
            return []
        estados = []
        selected_id = None
        try:
            live = self.app.get_tolvas_status()
            sel = next((t for t in live if t.get("seleccionada")), None) if live else None
            if sel:
                selected_id = int(sel.get("id", 0))
        except Exception:
            selected_id = None
        for idx, hopper in enumerate(hoppers_cfg):
            hopper_id = int(hopper.get("id", idx + 1))
            estados.append(
                {
                    "id": hopper_id,
                    "nombre": str(hopper.get("nombre", f"Tolva {hopper_id}")),
                    "seleccionada": hopper_id == selected_id if selected_id else idx == 0,
                    "trabada": False,
                }
            )
        if estados and not any(e["seleccionada"] for e in estados):
            estados[0]["seleccionada"] = True
        return estados


    def _eliminar_tolva_cards_obsoletas(self, active_ids):
        removed = False
        for tolva_id in list(self.tolva_cards.keys()):
            if tolva_id not in active_ids:
                try:
                    self.tolva_cards[tolva_id]["card"].destroy()
                except Exception:
                    pass
                del self.tolva_cards[tolva_id]
                removed = True
        if removed:
            self._last_tolvas_signature = None
        return removed


    def _layout_tolva_card(self, card, index, total):
        """Distribuye tarjetas en fila según cantidad de tolvas configuradas."""
        if total <= 1:
            card.grid(row=0, column=0, padx=10, pady=4, sticky="nsew")
            self.tolvas_cards_row.grid_columnconfigure(0, weight=1)
        else:
            cols = min(total, 3)
            row = index // cols
            col = index % cols
            card.grid(row=row, column=col, padx=8, pady=4, sticky="nsew")
            for c in range(cols):
                self.tolvas_cards_row.grid_columnconfigure(c, weight=1)


    def mostrar_menu_tolva(self, tolva_id):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(
            label="Calibración manual...",
            command=self.configurar_calibracion_tolvas,
        )
        try:
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()


    def actualizar_tolvas_gui(self):
        estados = self.app.get_tolvas_status()
        if not estados:
            estados = self._estados_tolvas_fallback()
        if not estados:
            if self._tolvas_section_title:
                self._tolvas_section_title.config(text="Tolvas: ninguna configurada en config.json")
            return

        n_tolvas = len(estados)
        if self._tolvas_section_title:
            plural = "tolva" if n_tolvas == 1 else "tolvas"
            self._tolvas_section_title.config(
                text=f"Tolvas ({n_tolvas} {plural}) — ← / → para seleccionar"
            )

        active_ids = {int(estado.get("id", 0)) for estado in estados}
        if active_ids != self._last_tolva_ids:
            self._last_tolva_ids = active_ids
            self._eliminar_tolva_cards_obsoletas(active_ids)

        signature = tuple(
            (
                int(estado.get("id", 0)),
                str(estado.get("nombre", "")),
                bool(estado.get("seleccionada")),
                bool(estado.get("trabada")),
            )
            for estado in estados
        )
        if signature == self._last_tolvas_signature:
            self.actualizar_estado_operacion_ui(estados_tolvas=estados)
            return

        for index, estado in enumerate(estados):
            tolva_id = int(estado["id"])
            if tolva_id not in self.tolva_cards:
                card = tk.Frame(self.tolvas_cards_row, bg="#ECEFF1", bd=0, highlightthickness=2)
                self._layout_tolva_card(card, index, n_tolvas)
                if self._is_admin_user():
                    gear_btn = tk.Button(
                        card,
                        text="⚙",
                        font=("Segoe UI", 10, "bold"),
                        bg="#D5D8DC",
                        fg="#2C3E50",
                        bd=0,
                        padx=6,
                        pady=2,
                        cursor="hand2",
                        command=lambda tid=tolva_id: self.mostrar_menu_tolva(tid),
                    )
                    gear_btn.place(relx=1.0, x=-8, y=6, anchor="ne")
                else:
                    gear_btn = None
                icon_canvas = tk.Canvas(card, width=86, height=58, bg="#ECEFF1", highlightthickness=0, bd=0)
                icon_canvas.pack(padx=12, pady=(8, 2))
                # Dibujo estilo hopper real: tolva superior, embudo y boquilla
                back_panel_id = icon_canvas.create_rectangle(
                    8, 7, 78, 17,
                    fill="#AEB6BF", outline="#8D99A6", width=1
                )
                body_id = icon_canvas.create_polygon(
                    14, 12, 72, 12, 62, 34, 24, 34,
                    fill="#95A5A6", outline="#7F8C8D", width=2
                )
                window_id = icon_canvas.create_rectangle(
                    28, 17, 58, 30,
                    fill="#D6DBDF", outline="#A6ACAF", width=1
                )
                mouth_id = icon_canvas.create_polygon(
                    35, 34, 51, 34, 48, 47, 38, 47,
                    fill="#95A5A6", outline="#7F8C8D", width=2
                )
                base_id = icon_canvas.create_rectangle(
                    31, 47, 55, 51,
                    fill="#626F7A", outline="#525C66", width=1
                )
                coin1_id = icon_canvas.create_oval(
                    32, 21, 40, 28,
                    fill="#F1C40F", outline="#D4AC0D", width=1
                )
                coin2_id = icon_canvas.create_oval(
                    43, 19, 51, 26,
                    fill="#F1C40F", outline="#D4AC0D", width=1
                )
                coin3_id = icon_canvas.create_oval(
                    42, 36, 49, 42,
                    fill="#F1C40F", outline="#D4AC0D", width=1
                )

                nombre_label = tk.Label(card, text=estado["nombre"], font=("Segoe UI", 11, "bold"), bg="#ECEFF1", fg="#2C3E50")
                nombre_label.pack(padx=12, pady=(2, 4))
                estado_label = tk.Label(card, text="", font=("Segoe UI", 10), bg="#ECEFF1", fg="#2C3E50")
                estado_label.pack(padx=12, pady=(0, 10))
                self.tolva_cards[tolva_id] = {
                    "card": card,
                    "icon_canvas": icon_canvas,
                    "back_panel_id": back_panel_id,
                    "body_id": body_id,
                    "window_id": window_id,
                    "mouth_id": mouth_id,
                    "base_id": base_id,
                    "coin1_id": coin1_id,
                    "coin2_id": coin2_id,
                    "coin3_id": coin3_id,
                    "nombre_label": nombre_label,
                    "estado_label": estado_label,
                    "gear_btn": gear_btn,
                }

            refs = self.tolva_cards[tolva_id]
            card = refs["card"]
            nombre_label = refs["nombre_label"]
            estado_label = refs["estado_label"]
            icon_canvas = refs["icon_canvas"]

            if estado["trabada"] and estado["seleccionada"]:
                bg_color = "#C0392B"  # rojo más oscuro para "cursor" sobre tolva trabada
                text_color = "white"
                estado_text = "SELECCIONADA / TRABADA"
                icon_color = "#F5B7B1"
                border_color = "#F1948A"
            elif estado["trabada"]:
                bg_color = "#E74C3C"
                text_color = "white"
                estado_text = "TRABADA"
                icon_color = "#FDEDEC"
                border_color = "#F5B7B1"
            elif estado["seleccionada"]:
                bg_color = "#2ECC71"
                text_color = "white"
                estado_text = "ACTIVA"
                icon_color = "#D5F5E3"
                border_color = "#A9DFBF"
            else:
                bg_color = "#ECEFF1"
                text_color = "#2C3E50"
                estado_text = "INACTIVA"
                icon_color = "#95A5A6"
                border_color = "#7F8C8D"

            card.config(bg=bg_color, highlightbackground=bg_color)
            icon_canvas.config(bg=bg_color)
            nombre_label.config(bg=bg_color, fg=text_color)
            estado_label.config(bg=bg_color, fg=text_color, text=estado_text)
            icon_canvas.itemconfig(refs["back_panel_id"], fill=icon_color, outline=border_color)
            icon_canvas.itemconfig(refs["body_id"], fill=icon_color, outline=border_color)
            icon_canvas.itemconfig(refs["window_id"], fill="#E5E8E8", outline=border_color)
            icon_canvas.itemconfig(refs["mouth_id"], fill=icon_color, outline=border_color)
            icon_canvas.itemconfig(refs["base_id"], fill="#626F7A", outline="#525C66")
            icon_canvas.itemconfig(refs["coin1_id"], fill="#F1C40F", outline="#D4AC0D")
            icon_canvas.itemconfig(refs["coin2_id"], fill="#F1C40F", outline="#D4AC0D")
            icon_canvas.itemconfig(refs["coin3_id"], fill="#F1C40F", outline="#D4AC0D")

        self._last_tolvas_signature = signature
        self.actualizar_estado_operacion_ui(estados_tolvas=estados)


    def actualizar_estado_operacion_ui(self, estados_tolvas=None):
        if estados_tolvas is None:
            estados_tolvas = self.app.get_tolvas_status()

        seleccionada = next((t for t in estados_tolvas if t.get("seleccionada")), None) if estados_tolvas else None
        trabada = bool(seleccionada and seleccionada.get("trabada"))
        motor_activo = bool(self._ms.get_motor_activo())
        motor_direccion = str(self._ms.get_motor_direccion() or "detenido").lower()
        pendientes = int(self._ms.get_fichas_restantes())

        if motor_activo:
            self.status_motor_lbl.config(text="Motor: ON", bg="#2ECC71", fg="white")
            if motor_direccion == "atras":
                self.status_motor_dir_lbl.config(text="Sentido: ATRAS", bg="#F39C12", fg="white")
            else:
                self.status_motor_dir_lbl.config(text="Sentido: ADELANTE", bg="#2E86C1", fg="white")
        else:
            self.status_motor_lbl.config(text="Motor: OFF", bg="#ECF0F1", fg="#2C3E50")
            self.status_motor_dir_lbl.config(text="Sentido: detenido", bg="#ECF0F1", fg="#2C3E50")

        if seleccionada:
            if trabada:
                self.status_tolva_lbl.config(text=f"Tolva: {seleccionada['nombre']} (TRABADA)", bg="#C0392B", fg="white")
            else:
                self.status_tolva_lbl.config(text=f"Tolva: {seleccionada['nombre']}", bg="#27AE60", fg="white")
        else:
            self.status_tolva_lbl.config(text="Tolva: -", bg="#ECF0F1", fg="#2C3E50")

        self.status_pendientes_lbl.config(text=f"Pendientes: {pendientes}")

        # Mantener el label grande de "Fichas Restantes" sincronizado aunque
        # el callback del core se pierda por cualquier motivo.
        try:
            self._actualizar_fichas_restantes_label(pendientes)
        except Exception:
            pass
        if self._ultimo_evento_core_ts:
            self.status_last_event_lbl.config(text=f"Últ. evento: {self._ultimo_evento_core_ts.strftime('%H:%M:%S')}")

        self._update_arduino_connection_label()


    def _update_arduino_connection_label(self):
        """Refleja en el header si el Arduino está conectado (verde) o no (rojo)."""
        try:
            if self.app.get_serial_status().get("connected"):
                self.status_arduino_lbl.config(
                    text="Arduino: OK",
                    bg="#2ECC71",
                    fg="white",
                    cursor="arrow",
                )
                self.status_mode_lbl.config(text="Modo: hardware", bg="#D5F5E3", fg="#145A32")
            else:
                self.status_arduino_lbl.config(
                    text="Arduino: sin conexión",
                    bg="#FADBD8",
                    fg="#922B21",
                    cursor="hand2",
                )
                self.status_mode_lbl.config(text="Modo: simulacion", bg="#FCF3CF", fg="#7D6608")
        except Exception:
            pass


    def mostrar_alerta_motor_trabado(self, fichas_pendientes):
        """Encola alerta de motor trabado (puede llamarse desde el hilo ESP32)."""
        self._enqueue_gui_event("motor_alert", int(fichas_pendientes or 0))


    def _show_motor_alert_dialog(self, fichas_pendientes):
        mensaje = (
            "⚠️ PRECAUCIÓN - MOTOR TRABADO ⚠️\n\n"
            "El motor lleva demasiado tiempo encendido sin dispensar.\n"
            f"Fichas pendientes: {fichas_pendientes}\n"
            "Por favor, verifique el mecanismo y libere la obstrucción."
        )
        messagebox.showwarning("⚠️ MOTOR TRABADO", mensaje)
        self.app.desbloquear_motor()

