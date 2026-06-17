"""Mixin GUI: actualización de pantalla y eventos."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class UiMixin:
    @staticmethod
    def _is_local_base_url(base_url: str) -> bool:
        lower = str(base_url or "").lower()
        return "127.0.0.1" in lower or "localhost" in lower


    def _apply_kiosk_window(self):
        """
        Tras destruir el Tk del login se crea una ventana nueva; en algunos entornos
        (Linux / labwc / Xwayland) el primer -fullscreen no aplica hasta que el WM
        mapeó la ventana. Forzamos geometry a pantalla y re-aplicamos fullscreen.
        """
        r = self.root
        try:
            r.update_idletasks()
        except Exception:
            pass
        try:
            sw = int(r.winfo_screenwidth())
            sh = int(r.winfo_screenheight())
            if sw > 64 and sh > 64:
                r.geometry(f"{sw}x{sh}+0+0")
        except Exception:
            pass
        try:
            r.attributes('-fullscreen', True)
        except Exception:
            pass


    def _python_executable(self) -> str:
        # preferir venv si existe
        venv_py = self._repo_root / ".venv" / "bin" / "python3"
        if venv_py.exists():
            return str(venv_py)
        return "python3" if os.name != "nt" else "python"


    def crear_contenedor_scrollable(self, parent):
        """Crea un frame con scrollbar vertical"""
        container = tk.Frame(parent, bg=self.colors["bg"])
        
        canvas = tk.Canvas(container, bg=self.colors["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        
        scrollable_frame = tk.Frame(canvas, bg=self.colors["bg"])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def configure_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)
        
        canvas.bind("<Configure>", configure_canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        container.canvas = canvas
        
        # Frame interno con padding
        content_frame = tk.Frame(scrollable_frame, bg=self.colors["bg"])
        content_frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        return container, content_frame


    def mostrar_frame(self, frame):
        for f in [self.main_frame, self.contadores_page, self.config_frame, self.reportes_frame, self.simulacion_frame]:
            f.pack_forget()
        frame.pack(fill="both", expand=True)
        self._active_page = self._frame_to_page.get(frame, "other")

        # En pantallas táctiles a veces el primer cambio de vista queda "a medio render".
        # Forzamos layout para que el contenido aparezca completo sin doble toque.
        try:
            self.root.update_idletasks()
        except Exception:
            pass

        if hasattr(frame, 'canvas'):
            self.current_canvas = frame.canvas
            try:
                frame.canvas.update_idletasks()
                frame.canvas.configure(scrollregion=frame.canvas.bbox("all"))
            except Exception:
                pass
            frame.canvas.yview_moveto(0)
        else:
            self.current_canvas = None

        # Render bajo demanda: refrescar pesado sólo cuando la página lo usa.
        try:
            if self._active_page in ("main", "contadores"):
                self.actualizar_contadores_gui()
            if self._active_page == "main":
                self.actualizar_tolvas_gui()
        except Exception:
            pass

        try:
            self._apply_kiosk_window()
        except Exception:
            pass

    @staticmethod

    def _trigger_action(func):
        """Ejecuta una función y previene comportamiento por defecto."""
        func()
        return "break"


    def _is_admin_user(self) -> bool:
        return str(getattr(self, "username", "") or "").strip().lower() == "admin"


    def _evento_a_tecla_bind(event):
        """
        Convierte un evento de tecla Tkinter al formato de bind usado por la app.
        Ejemplos: "<KP_Divide>", "<minus>", "x", "X".
        """
        keysym = str(getattr(event, "keysym", "") or "").strip()
        char = str(getattr(event, "char", "") or "")
        if not keysym and not char:
            return ""

        special_names = {
            "slash",
            "minus",
            "asterisk",
            "KP_Divide",
            "KP_Subtract",
            "KP_Multiply",
            "KP_Add",
            "Return",
            "KP_Enter",
            "space",
        }
        if keysym.startswith("KP_") or keysym in special_names:
            return f"<{keysym}>"

        # Letras/números/teclas imprimibles simples.
        if len(char) == 1 and char.isprintable() and not char.isspace():
            return char

        # Fallback para teclas especiales no imprimibles.
        return f"<{keysym}>"


    def _start_gui_main_loop(self):
        """Procesa eventos GUI encolados desde hilos del motor/ESP32/red."""
        if self._is_shutting_down:
            return
        self._poll_gui_main_queue()


    def _poll_gui_main_queue(self):
        if self._is_shutting_down:
            return
        sync = False
        network_status = None
        motor_alert = None
        while True:
            try:
                kind, payload = self._gui_main_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "sync":
                sync = True
            elif kind == "network":
                network_status = payload
            elif kind == "motor_alert":
                motor_alert = payload
        if sync:
            self._apply_sync_from_core()
        if network_status is not None:
            self.actualizar_estado_red_ui(network_status)
        if motor_alert is not None:
            self._show_motor_alert_dialog(motor_alert)
        try:
            self._gui_poll_after_id = self.root.after(20, self._poll_gui_main_queue)
        except Exception:
            self._gui_poll_after_id = None


    def _enqueue_gui_event(self, kind, payload=None):
        if self._is_shutting_down:
            return
        try:
            self._gui_main_queue.put_nowait((kind, payload))
        except queue.Full:
            pass


    def sincronizar_desde_core(self):
        """
        Llamada desde el hilo del motor/ESP32 cuando cambian contadores.
        Encola trabajo para el hilo principal (Tkinter no es thread-safe).
        """
        if self._gui_sync_scheduled:
            return
        self._gui_sync_scheduled = True
        self._enqueue_gui_event("sync")


    def _apply_sync_from_core(self):
        self._gui_sync_scheduled = False
        self._ultimo_evento_core_ts = datetime.now()

        for attr in self._ms.drain_token_attributions():
            self._aplicar_atribucion_token(attr)

        fichas_restantes_hw = self._ms.get_fichas_restantes()
        fichas_expendidas_hw = max(0, int(self._ms.get_fichas_sesion()))

        nuevo_parcial = max(0, self.inicio_parcial_fichas + fichas_expendidas_hw)
        nuevo_global = max(0, self.inicio_apertura_fichas + fichas_expendidas_hw)

        contadores_cambiaron = False
        if nuevo_parcial != self.contadores_parcial["fichas_expendidas"]:
            self.contadores_parcial["fichas_expendidas"] = nuevo_parcial
            self.contadores_global["fichas_expendidas"] = nuevo_global
            contadores_cambiaron = True

        if fichas_restantes_hw != self.contadores["fichas_restantes"]:
            self.contadores["fichas_restantes"] = fichas_restantes_hw
            contadores_cambiaron = True

        if contadores_cambiaron:
            if self._active_page in ("main", "contadores"):
                self.actualizar_contadores_gui()
            self._persistir_estado_critico("sync_core")

        if self._active_page == "main":
            self.actualizar_tolvas_gui()


    def _hoppers_configurados(self):
        hoppers = self.maquina_hoppers if isinstance(self.maquina_hoppers, list) else []
        return [h for h in hoppers if isinstance(h, dict)]


    def _set_modal_grab(self, window, retries=20, retry_delay_ms=100):
        """
        Aplica grab_set solo cuando el Toplevel ya es visible.
        En algunos entornos (X11 remoto/kiosk) el mapeo de ventana tarda unos ms.
        """
        try:
            window.update_idletasks()
            window.deiconify()
            window.lift()
        except tk.TclError:
            return

        grab_aplicado = {"done": False}

        def _try_apply_grab() -> bool:
            if grab_aplicado["done"] or not window.winfo_exists():
                return True
            if not window.winfo_viewable():
                return False
            try:
                window.grab_set()
                grab_aplicado["done"] = True
                return True
            except tk.TclError:
                return False

        def _on_map(_event=None):
            _try_apply_grab()

        window.bind("<Map>", _on_map, add="+")

        def _try_grab(remaining):
            if not window.winfo_exists():
                return
            if _try_apply_grab():
                return

            if remaining > 0:
                window.after(retry_delay_ms, lambda: _try_grab(remaining - 1))
            else:
                print("[GUI] Aviso: no se pudo aplicar grab_set (ventana no visible).")

        window.after(0, lambda: _try_grab(retries))


    def _cancel_after(self, attr_name):
        after_id = getattr(self, attr_name, None)
        if not after_id:
            return
        try:
            self.root.after_cancel(after_id)
        except Exception:
            pass
        setattr(self, attr_name, None)


    def _shutdown_ui(self, destroy_root=True):
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        try:
            self._persistir_estado_critico("shutdown")
            self.guardar_configuracion(inmediato=True)
        except Exception as exc:
            print(f"[GUI] Aviso persistiendo al cerrar: {exc}")
        try:
            self.network_service.stop()
        except Exception:
            pass
        self._cancel_after("_after_id")
        self._cancel_after("_after_fast_status_id")
        self._cancel_after("_gui_poll_after_id")
        self._gui_sync_scheduled = False
        while True:
            try:
                self._gui_main_queue.get_nowait()
            except queue.Empty:
                break
        if destroy_root:
            try:
                self.root.destroy()
            except Exception:
                pass


    def _on_window_close(self):
        self._shutdown_ui(destroy_root=True)


    def actualizar_contadores_gui(self):
        for key in self.contadores_labels:
            valor = self.contadores[key]
            # Formatear dinero con decimales, el resto como entero
            # Actualizado para el nuevo diseño de cards (solo valor)
            if key == "dinero_ingresado":
                texto = f"${valor:.2f}"
            else:
                texto = f"{int(valor)}"
            self.contadores_labels[key].config(text=texto)


    def actualizar_fecha_hora(self):
        # Obtener la fecha y hora actual
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S")
        self.footer_label.config(text=current_time)  # Actualizar el label del footer
        if self._active_page == "main":
            self.actualizar_estado_operacion_ui()
        # Refresco defensivo de tolvas SOLO si no llega callback del core por unos segundos.
        stale_tolvas = (
            self._ultimo_evento_core_ts is None
            or (now - self._ultimo_evento_core_ts).total_seconds() >= 3.0
        )
        if stale_tolvas and self._active_page == "main":
            self.actualizar_tolvas_gui()
        # Check de updates (cada ~30s, no bloqueante)
        if (time.time() - self._update_last_check_ts) > 30:
            self._update_last_check_ts = time.time()
            self._check_updates_async()
        self._after_id = self.root.after(1000, self.actualizar_fecha_hora)  # Llamar a esta función cada segundo
