"""Mixin GUI: layout principal (estado + composición)."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403
from expendedora.interface.gui.mixins.layout_pages_mixin import LayoutPagesMixin
from expendedora.interface.gui.mixins.layout_finish_mixin import LayoutFinishMixin


class LayoutMixin(LayoutPagesMixin, LayoutFinishMixin):
    def __init__(self, root, username, controlador=None, cashier_id=None, on_logout=None):
        self.root = root
        self.username = username
        self.cashier_id = cashier_id
        self.on_logout = on_logout
        self._is_shutting_down = False
        self.app: AppController = controlador or create_app_controller()
        self._ms = self.app.machine_state
        self.root.title("Expendedora - Control") # El título no será visible
        self.root.attributes('-fullscreen', True) # Ocupa 100% de pantalla y oculta la barra de título
        self.root.configure(bg="#F4F7F6")
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # --- ESTILOS ---
        self.colors = {
            "bg": "#F4F7F6",
            "sidebar": "#2C3E50",
            "header": "#FFFFFF",
            "card": "#FFFFFF",
            "text": "#34495E",
            "primary": "#3498DB",
            "success": "#2ECC71",
            "warning": "#F39C12",
            "danger": "#E74C3C",
            "text_light": "#ECF0F1"
        }
        self.fonts = {
            "h1": ("Segoe UI", 24, "bold"),
            "h2": ("Segoe UI", 18, "bold"),
            "body": ("Segoe UI", 12),
            "big": ("Segoe UI", 32, "bold")
        }

        # Inicializar variables de configuración
        self.config_file = self.app.config_path
        self.shortcuts_file = str((Path(__file__).resolve().parent / "atajos_promociones.json"))
        self.config_repository = self.app.config_repository
        self.counter_service = self.app.counter_service
        self.session_service = self.app.session_service

        self.promociones = {
            "Promo 1": {"precio": 0, "fichas": 0},
            "Promo 2": {"precio": 0, "fichas": 0},
            "Promo 3": {"precio": 0, "fichas": 0}
        }
        self.valor_ficha = 1.0
        self.device_id = ""
        self.codigo_hardware = ""
        self.dni_admin = DEFAULT_DNI_ADMIN
        self.api_config = {}
        self.heartbeat_intervalo_s = 600
        self.maquina_hoppers = []
        self.operacion_config = {"ultima_apertura_fecha": ""}
        self.atajos_promociones = {k: list(v) for k, v in DEFAULT_PROMO_HOTKEYS.items()}
        self.network_manager_cfg = {
            "enabled": True,
            "check_interval_s": 8,
            "reconnect_after_failures": 3,
            "backend_timeout_s": 3.0,
            "internet_host": "8.8.8.8",
            "backend_url": "",
            "preferred_interface": "",
            "wifi_ssid": "",
            "wifi_password": "",
        }
        self._promo_binding_candidates = set()
        self._promo_last_trigger_ts: dict[str, float] = {}
        self._entries_operativos = []
        self._network_status_ui = {}
        self.network_service = self.app.network_service
        self.report_repository = self.app.report_repository

        # Contadores contables (nuevo esquema):
        # - global: cierre diario
        # - parcial: sesión/cajero y reportes operativos
        self.contadores_global = self.counter_service.default_counters()
        self.contadores_parcial = self.counter_service.default_counters()
        self.inicio_apertura_fichas = 0
        self.inicio_parcial_fichas = 0
        self._sync_counter_aliases()

        # --- Cola hilo principal: el bridge ESP32 NO puede llamar root.after() ---
        self._gui_main_queue = queue.Queue()
        self._gui_sync_scheduled = False
        self._gui_poll_after_id = None
        self._guardar_config_timer = None          # Timer para debounce de guardar_configuracion
        
        self.cargar_configuracion()
        self._aplicar_estado_recuperado()
        self._recalcular_bases_contadores()
        
        # Configuración de Scroll Global
        self.current_canvas = None
        def _on_mousewheel(event):
            if self.current_canvas:
                if event.num == 5 or event.delta < 0:
                    self.current_canvas.yview_scroll(1, "units")
                elif event.num == 4 or event.delta > 0:
                    self.current_canvas.yview_scroll(-1, "units")
        
        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        self.root.bind_all("<Button-4>", _on_mousewheel)
        self.root.bind_all("<Button-5>", _on_mousewheel)
        
        # Registrar función de actualización con el core
        self.app.on_state_changed(self.sincronizar_desde_core)
        self.app.on_motor_alert(self.mostrar_alerta_motor_trabado)
        self.root.after(0, self._start_gui_main_loop)

        # Header
        self.header_frame = tk.Frame(root, bg=self.colors["header"], height=76)
        self.header_frame.pack(side="top", fill="x")
        # Línea separadora
        tk.Frame(root, bg="#E0E0E0", height=1).pack(side="top", fill="x")

        self.header_title_frame = tk.Frame(self.header_frame, bg=self.colors["header"])
        self.header_title_frame.pack(side="left", fill="y", padx=20, pady=10)
        tk.Label(
            self.header_title_frame,
            text="Expendedora",
            bg=self.colors["header"],
            fg=self.colors["text"],
            font=self.fonts["h2"],
        ).pack(anchor="w")
        tk.Label(
            self.header_title_frame,
            text=f"Usuario: {username}",
            bg=self.colors["header"],
            fg="#7F8C8D",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        self.header_status_frame = tk.Frame(self.header_frame, bg=self.colors["header"])
        self.header_status_frame.pack(side="right", padx=20, pady=10)
        self.status_motor_lbl = tk.Label(self.header_status_frame, text="Motor: OFF", bg="#ECF0F1", fg="#2C3E50", font=("Segoe UI", 9, "bold"), padx=10, pady=4)
        self.status_motor_lbl.pack(side="left", padx=4)
        self.status_motor_dir_lbl = tk.Label(
            self.header_status_frame,
            text="Sentido: detenido",
            bg="#ECF0F1",
            fg="#2C3E50",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.status_motor_dir_lbl.pack(side="left", padx=4)
        self.status_tolva_lbl = tk.Label(self.header_status_frame, text="Tolva: -", bg="#ECF0F1", fg="#2C3E50", font=("Segoe UI", 9, "bold"), padx=10, pady=4)
        self.status_tolva_lbl.pack(side="left", padx=4)
        self.status_pendientes_lbl = tk.Label(self.header_status_frame, text="Pendientes: 0", bg="#ECF0F1", fg="#2C3E50", font=("Segoe UI", 9, "bold"), padx=10, pady=4)
        self.status_pendientes_lbl.pack(side="left", padx=4)
        self.status_last_event_lbl = tk.Label(self.header_status_frame, text="Últ. evento: -", bg="#ECF0F1", fg="#2C3E50", font=("Segoe UI", 9, "bold"), padx=10, pady=4)
        self.status_last_event_lbl.pack(side="left", padx=4)
        self.status_network_lbl = tk.Label(
            self.header_status_frame,
            text="Red: ...",
            bg="#D6EAF8",
            fg="#1B4F72",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            anchor="w",
        )
        # En pantallas chicas este label se recorta fácil.
        # Permitimos que expanda y use el espacio sobrante del header.
        self.status_network_lbl.pack(side="left", padx=4, fill="x", expand=True)
        self.status_arduino_lbl = tk.Label(
            self.header_status_frame,
            text="Arduino: -",
            bg="#ECF0F1",
            fg="#2C3E50",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
        )
        self.status_arduino_lbl.pack(side="left", padx=4)
        self.status_arduino_lbl.bind("<Button-1>", lambda _e: self._on_click_status_arduino())
        self.status_mode_lbl = tk.Label(
            self.header_status_frame,
            text="Modo: -",
            bg="#ECF0F1",
            fg="#2C3E50",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.status_mode_lbl.pack(side="left", padx=4)

        def _destrabar_tolva_seleccionada():
            try:
                self.app.solicitar_destrabe()
                messagebox.showinfo("Destrabar", "Se solicitó destrabe (retroceso) en la tolva seleccionada.")
            except Exception as e:
                messagebox.showerror("Destrabar", f"No se pudo solicitar destrabe: {e}")

        self.btn_destrabar = tk.Button(
            self.header_status_frame,
            text="Destrabar",
            command=_destrabar_tolva_seleccionada,
            bg="#F39C12",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            bd=0,
            padx=14,
            pady=6,
            activebackground="#D68910",
            activeforeground="white",
            cursor="hand2",
        )
        self.btn_destrabar.pack(side="left", padx=6)
        self._ultimo_evento_core_ts = None
        self._after_fast_status_id = None
        self._fast_status_interval_ms = 120
        self._last_tolvas_signature = None
        self._last_tolva_ids = None
        self._tolvas_section_title = None
        self._active_page = "main"
        self._frame_to_page = {}

        # Footer antes del sidebar/contenido para que ambos terminen a la misma altura.
        from expendedora.interface.gui.constants import GUI_FOOTER_HEIGHT

        self.footer_frame = tk.Frame(root, bg=self.colors["sidebar"], height=GUI_FOOTER_HEIGHT)
        self.footer_frame.pack(side="bottom", fill="x")
        self.footer_frame.pack_propagate(False)

        self.taskbar_frame = tk.Frame(self.footer_frame, bg=self.colors["sidebar"])
        self.taskbar_frame.pack(fill="both", expand=True, padx=12, pady=6)
        self._build_help_taskbar(self.taskbar_frame)

        self.footer_label = tk.Label(
            self.taskbar_frame,
            text="",
            bg=self.colors["sidebar"],
            fg="#BDC3C7",
            font=("Segoe UI", 10),
        )
        self.footer_label.pack(side="right")

        self._build_layout_pages(root)
        self._finalize_layout(root, username)

    def _tick_fast_status(self) -> None:
        """Refresco rápido de pendientes/restantes en header y card principal."""
        try:
            pendientes = int(self._ms.get_fichas_restantes())
            motor_activo = bool(self._ms.get_motor_activo())
            motor_direccion = str(self._ms.get_motor_direccion() or "detenido").lower()
            self.status_pendientes_lbl.config(text=f"Pendientes: {pendientes}")
            if motor_activo:
                self.status_motor_lbl.config(text="Motor: ON", bg="#2ECC71", fg="white")
                if motor_direccion == "atras":
                    self.status_motor_dir_lbl.config(text="Sentido: ATRAS", bg="#F39C12", fg="white")
                else:
                    self.status_motor_dir_lbl.config(text="Sentido: ADELANTE", bg="#2E86C1", fg="white")
            else:
                self.status_motor_lbl.config(text="Motor: OFF", bg="#ECF0F1", fg="#2C3E50")
                self.status_motor_dir_lbl.config(text="Sentido: detenido", bg="#ECF0F1", fg="#2C3E50")

            self.contadores["fichas_restantes"] = pendientes
            label = self.contadores_labels.get("fichas_restantes")
            if label is not None:
                label.config(text=f"{pendientes}")
            self._update_arduino_connection_label()
        except Exception:
            pass
        self._after_fast_status_id = self.root.after(self._fast_status_interval_ms, self._tick_fast_status)

    def _start_fast_status_poll(self) -> None:
        self._tick_fast_status()
