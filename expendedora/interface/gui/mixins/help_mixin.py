"""Mixin GUI: manual de usuario y ayuda rápida (barra inferior)."""

from expendedora.interface.gui.help_content import HELP_SCENARIOS
from expendedora.interface.gui.manual_markdown import open_manual_window
from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class HelpMixin:
    def _build_help_taskbar(self, parent: tk.Frame) -> None:
        """Controles de ayuda en la barra inferior (izquierda)."""
        btn_style = dict(
            bg="#34495E",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            bd=0,
            padx=12,
            pady=4,
            activebackground="#2C3E50",
            activeforeground="white",
            cursor="hand2",
            relief="flat",
        )

        tk.Button(
            parent,
            text="Manual",
            command=self.abrir_manual_usuario,
            **btn_style,
        ).pack(side="left")

        self._help_menu_btn = tk.Menubutton(
            parent,
            text="Ayuda  ▾",
            direction="below",
            highlightthickness=0,
            **btn_style,
        )
        self._help_menu_btn.pack(side="left", padx=(8, 0))

        help_menu = tk.Menu(
            self._help_menu_btn,
            tearoff=0,
            font=("Segoe UI", 10),
            activebackground="#3498DB",
            activeforeground="white",
        )
        for scenario in HELP_SCENARIOS:
            help_menu.add_command(
                label=scenario.label,
                command=lambda action=scenario.action: self._run_help_scenario(action),
            )
        self._help_menu_btn.config(menu=help_menu)

    def _run_help_scenario(self, action: str) -> None:
        handler = getattr(self, action, None)
        if callable(handler):
            handler()

    def abrir_manual_usuario(self) -> None:
        if getattr(self, "_manual_window", None) is not None:
            try:
                if self._manual_window.winfo_exists():
                    self._manual_window.lift()
                    self._manual_window.focus_force()
                    return
            except tk.TclError:
                pass

        def _on_close() -> None:
            self._manual_window = None

        self._manual_window = open_manual_window(
            self.root,
            colors=self.colors,
            fonts=self.fonts,
            on_close=_on_close,
        )

    def help_fichas_no_cuentan(self) -> None:
        pendientes = int(self._ms.get_fichas_restantes())
        detalle = (
            "Si las fichas salen físicamente pero el contador no baja, "
            "puede haber desincronización con el Arduino.\n\n"
            "Se reiniciará la conexión serial. Luego podrá confirmar "
            "si desea reintentar la venta pendiente."
        )
        if pendientes > 0:
            detalle += f"\n\nHay {pendientes} ficha(s) pendientes en buffer."

        if not messagebox.askyesno("Fichas no se cuentan", f"{detalle}\n\n¿Continuar?"):
            return

        ok = self.app.force_reconnect()
        self._update_arduino_connection_label()
        try:
            self.root.update_idletasks()
        except Exception:
            pass

        if not ok:
            messagebox.showwarning(
                "Fichas no se cuentan",
                "No se pudo reconectar el Arduino.\n"
                "Verifique cable USB y puerto COM, luego reintente.",
            )
            return

        pendientes_despues = int(self._ms.get_fichas_restantes())
        if pendientes_despues <= 0:
            messagebox.showinfo(
                "Fichas no se cuentan",
                "Arduino reconectado.\n\n"
                "No hay venta pendiente en buffer. "
                "Vuelva a cargar la cantidad en Expendio manual.",
            )
            return

        if messagebox.askyesno(
            "Reintentar venta",
            f"Arduino reconectado.\n\n"
            f"Quedan {pendientes_despues} ficha(s) pendientes.\n"
            "¿Confirmar reintento de dispensado?",
        ):
            self._ms.set_motor_activo(True)
            self._ms.set_motor_direccion("adelante")
            self.actualizar_estado_operacion_ui()
            messagebox.showinfo(
                "Reintentar venta",
                "Dispensado reanudado. Observe el contador de fichas restantes.",
            )
        else:
            messagebox.showinfo(
                "Reintentar venta",
                "Reconexión lista. Puede reintentar cuando confirme que la tolva está OK.",
            )

    def help_motor_trabado(self) -> None:
        if not messagebox.askyesno(
            "Motor trabado",
            "Se intentará destrabar: hasta 3 ciclos adelante + retroceso.\n"
            "Si sale una ficha de prueba, no se cuenta en la venta.\n\n"
            "¿Continuar?",
        ):
            return

        pendientes_antes = int(self._ms.get_fichas_restantes())
        expendidas_antes = int(self.contadores.get("fichas_expendidas", 0))

        try:
            self.app.solicitar_destrabe()
            self.actualizar_estado_operacion_ui()
        except Exception as exc:
            messagebox.showerror("Motor trabado", f"No se pudo solicitar destrabe:\n{exc}")
            return

        deadline = time.time() + 18.0

        def _verificar_salida() -> None:
            if self.app.test_token_destrabe_ok():
                messagebox.showinfo(
                    "Motor trabado",
                    "Tolva destrabada: salió una ficha de prueba (no se cuenta en la venta).\n"
                    "Si aún hay fichas pendientes, el expendio debería continuar.",
                )
                return
            pendientes_despues = int(self._ms.get_fichas_restantes())
            expendidas_despues = int(self.contadores.get("fichas_expendidas", 0))
            if pendientes_despues < pendientes_antes or expendidas_despues > expendidas_antes:
                messagebox.showinfo(
                    "Motor trabado",
                    "Se detectó actividad del dispensador.\n"
                    "Si aún hay fichas pendientes, el expendio debería continuar.",
                )
                return
            if time.time() < deadline:
                self.root.after(500, _verificar_salida)
                return
            messagebox.showwarning(
                "Motor trabado",
                "No se detectó salida de ficha de prueba.\n\n"
                "Solicite atención de un técnico.",
            )

        self.root.after(500, _verificar_salida)

    def help_arduino_sin_conexion(self) -> None:
        status = self.app.get_serial_status()
        if status.get("connected"):
            messagebox.showinfo(
                "Arduino",
                "El Arduino aparece conectado.\n"
                "Si el problema persiste, use «¿Las fichas salen pero no se cuentan?».",
            )
            return
        self._on_click_status_arduino()

    def help_pendientes_atascadas(self) -> None:
        pendientes = int(self._ms.get_fichas_restantes())
        if pendientes <= 0:
            messagebox.showinfo(
                "Fichas pendientes",
                "No hay fichas pendientes en el buffer.",
            )
            return

        opcion = messagebox.askyesnocancel(
            "Fichas pendientes atascadas",
            f"Hay {pendientes} ficha(s) pendientes.\n\n"
            "Sí = Reconectar Arduino y reintentar dispensado\n"
            "No = Anular venta (vaciar buffer)\n"
            "Cancelar = Volver",
        )
        if opcion is None:
            return
        if opcion:
            self.help_fichas_no_cuentan()
        else:
            self.vaciar_buffer_dispensa_gui()

    def help_reiniciar_app(self) -> None:
        messagebox.showinfo(
            "Reiniciar aplicación",
            "Para recuperar la interfaz:\n\n"
            "1. Use «Cerrar sesión» en el menú lateral.\n"
            "2. Vuelva a ingresar con su usuario.\n\n"
            "En kiosco, el launcher vuelve a abrir la app automáticamente "
            "si se cierra por completo.",
        )
