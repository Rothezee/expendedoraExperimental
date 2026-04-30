import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
import os
import subprocess
import time
from pathlib import Path
import requests
from expendedora_core import CoreController
import shared_buffer
from infra.config_repository import ConfigRepository, DEFAULT_DNI_ADMIN
from infra.db_exception_message import format_db_exception
from infra.report_repository_mysql import ReportRepositoryMySQL
from services.counter_service import CounterService
from services.network_manager_service import NetworkManagerService
from services.session_service import SessionService

urlCierresLocal = "AdministrationPanel/src/expendedora/insert_close_expendedora.php"  # URL DE CIERRES (LOCAL)
urlCierresCloud = "src/expendedora/insert_close_expendedora.php"  # URL DE CIERRES (CLOUD)
urlDatos = "esp32_project/expendedora/insert_data_expendedora.php"  # URL DE REPORTES
urlSubcierreLocal = "AdministrationPanel/src/expendedora/insert_subcierre_expendedora.php"  # URL DE SUBCIERRES (LOCAL)
urlSubcierreCloud = "src/expendedora/insert_subcierre_expendedora.php"  # URL DE SUBCIERRES (CLOUD)
DNS = "https://app.maquinasbonus.com/"  # DNS servidor
DNSLocal = "http://127.0.0.1/"  # DNS servidor local

DEFAULT_PROMO_HOTKEYS = {
    "Promo 1": ["<slash>", "<KP_Divide>"],
    "Promo 2": ["<asterisk>", "<KP_Multiply>", "x", "X"],
    "Promo 3": ["<minus>", "<KP_Subtract>"],
}

import threading as _threading

def _post_en_hilo(url, datos, descripcion="", retry_without_cashier_id=False):
    """
    Envía un POST HTTP en un hilo separado con timeout.
    Nunca bloquea el hilo de Tkinter aunque no haya internet.
    """
    def _enviar():
        try:
            resp = requests.post(url, json=datos, timeout=5)
            print(f"[NET] {descripcion} → {resp.status_code}")
            body_preview = ""
            if resp.status_code >= 400:
                body_preview = str(resp.text or "").strip().replace("\n", " ")
                if len(body_preview) > 240:
                    body_preview = f"{body_preview[:240]}..."
                print(f"[NET WARN] {descripcion} body: {body_preview or '-'}")

            # Compatibilidad backend remoto: si id_cajero no coincide entre entornos
            # reintentamos usando usuario (employee_id/usuario_cajero) sin id numérico.
            if (
                retry_without_cashier_id
                and resp.status_code == 404
                and "cajero no encontrado" in (body_preview or "").lower()
                and isinstance(datos, dict)
                and "id_cajero" in datos
            ):
                retry_payload = dict(datos)
                retry_payload.pop("id_cajero", None)
                retry_desc = f"{descripcion} (retry sin id_cajero)"
                retry_resp = requests.post(url, json=retry_payload, timeout=5)
                print(f"[NET] {retry_desc} → {retry_resp.status_code}")
                if retry_resp.status_code >= 400:
                    retry_body = str(retry_resp.text or "").strip().replace("\n", " ")
                    if len(retry_body) > 240:
                        retry_body = f"{retry_body[:240]}..."
                    print(f"[NET WARN] {retry_desc} body: {retry_body or '-'}")
        except requests.exceptions.RequestException as e:
            print(f"[NET ERROR] {descripcion}: {e}")
    _threading.Thread(target=_enviar, daemon=True).start()

class ExpendedoraGUI:
    def __init__(self, root, username, core_controller=None, cashier_id=None, on_logout=None):
        self.root = root
        self.username = username
        self.cashier_id = cashier_id
        self.on_logout = on_logout
        self._is_shutting_down = False
        self.core = core_controller or CoreController()
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
        self.config_file = "config.json"
        self.config_repository = ConfigRepository(self.config_file)
        self.counter_service = CounterService()
        self.session_service = SessionService()

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
        }
        self._promo_binding_candidates = set()
        self._entries_operativos = []
        self._network_status_ui = {}
        self.network_service = NetworkManagerService(self.config_repository)
        self.report_repository = ReportRepositoryMySQL(self.config_repository)

        # Contadores de la página principal
        self.contadores = self.counter_service.default_counters()

        # Contadores de apertura
        self.contadores_apertura = self.counter_service.default_counters()

        # Contadores parciales
        self.contadores_parciales = self.counter_service.default_counters()


        # Flag para controlar si se realizó un cierre del día
        self.cierre_realizado = False
        self.contadores_parciales_pre_cierre = {}
        
        # --- ANTI-FLOOD: evita encolar root.after duplicados y guardar config en cada ficha ---
        self._after_sincronizar_pendiente = False  # True si ya hay un callback en cola
        self._guardar_config_timer = None          # Timer para debounce de guardar_configuracion
        
        self.cargar_configuracion()
        
        # Inicializar bases para contadores (Modelo: Base + Sesión)
        self.inicio_fichas_expendidas = self.contadores["fichas_expendidas"]
        self.inicio_apertura_fichas = self.contadores_apertura["fichas_expendidas"]
        self.inicio_parcial_fichas = self.contadores_parciales["fichas_expendidas"]
        
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
        self.core.register_gui_update(self.sincronizar_desde_core)
        self.core.register_gui_motor_alert(self.mostrar_alerta_motor_trabado)
        shared_buffer.set_gui_update_callback(self.sincronizar_desde_core)

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
        # En Raspberry con resoluciones chicas, este label se recorta fácil.
        # Permitimos que expanda y use el espacio sobrante del header.
        self.status_network_lbl.pack(side="left", padx=4, fill="x", expand=True)

        def _destrabar_tolva_seleccionada():
            try:
                self.core.request_unjam()
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
        self._auto_calib_after_id = None
        self._fast_status_interval_ms = 120
        self._last_tolvas_signature = None
        self._active_page = "main"
        self._frame_to_page = {}

        def _refresh_fast_status():
            """
            Refresco rápido (poll) de pendientes/restantes.
            Objetivo: UI responsiva (~50ms) sin depender de timers de 1s
            ni de la llegada del callback del core.
            """
            try:
                pendientes = int(shared_buffer.get_fichas_restantes())
                self.status_pendientes_lbl.config(text=f"Pendientes: {pendientes}")

                # Mantener el label grande de "Fichas Restantes" sincronizado.
                self.contadores["fichas_restantes"] = pendientes
                label = self.contadores_labels.get("fichas_restantes")
                if label is not None:
                    label.config(text=f"{pendientes}")
            except Exception:
                # No romper el loop de UI si algún widget todavía no existe.
                pass
            self._after_fast_status_id = self.root.after(self._fast_status_interval_ms, _refresh_fast_status)

        

        # Menú lateral
        self.menu_frame = tk.Frame(root, width=250, bg=self.colors["sidebar"])
        self.menu_frame.pack(side="left", fill="y")
        self.menu_frame.pack_propagate(False)

        tk.Label(self.menu_frame, text="MENÚ PRINCIPAL", bg=self.colors["sidebar"], fg="#95A5A6", font=("Segoe UI", 10, "bold")).pack(pady=(30, 10), padx=20, anchor="w")

        def crear_boton_menu(texto, comando, color_bg=self.colors["sidebar"]):
            btn = tk.Button(self.menu_frame, text=texto, bg=color_bg, fg="white", font=self.fonts["body"], 
                            bd=0, activebackground="#34495E", activeforeground="white", command=comando, anchor="w", padx=20, pady=10, cursor="hand2")
            btn.pack(fill="x", pady=1)
            return btn

        crear_boton_menu("Inicio", lambda: self.mostrar_frame(self.main_frame))
        crear_boton_menu("Contadores", lambda: self.mostrar_frame(self.contadores_page))
        
        if self.username == "admin":
            crear_boton_menu("Configuración", lambda: self.mostrar_frame(self.config_frame))
            
        crear_boton_menu("Cierre y Reportes", lambda: self.mostrar_frame(self.reportes_frame))
        
        if self.username == "admin":
            crear_boton_menu("Simulación", lambda: self.mostrar_frame(self.simulacion_frame))
            
        tk.Frame(self.menu_frame, bg=self.colors["sidebar"], height=20).pack() # Espaciador
        crear_boton_menu("Cerrar Sesión", self.cerrar_sesion, color_bg=self.colors["danger"])

        # Página principal
        self.main_frame, main_content = self.crear_contenedor_scrollable(root)

        tk.Label(main_content, text="Panel de Control", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["text"]).pack(anchor="w", pady=(0, 12))
        tk.Label(
            main_content,
            text="Estado rápido: verde activa, rojo trabada, rojo oscuro seleccionada trabada.",
            font=("Segoe UI", 10),
            bg=self.colors["bg"],
            fg="#7F8C8D",
        ).pack(anchor="w", pady=(0, 12))

        # --- Estado de tolvas ---
        self.tolvas_frame = tk.Frame(main_content, bg=self.colors["bg"])
        self.tolvas_frame.pack(fill="x", pady=(0, 15))
        tk.Label(
            self.tolvas_frame,
            text="Tolvas (← / → para seleccionar)",
            font=("Segoe UI", 11, "bold"),
            bg=self.colors["bg"],
            fg="#7F8C8D",
        ).pack(anchor="w", padx=10, pady=(0, 6))
        self.tolva_cards = {}
        self.tolvas_cards_row = tk.Frame(self.tolvas_frame, bg=self.colors["bg"])
        self.tolvas_cards_row.pack(fill="x")

        # --- Cards de Fichas (Inicio) ---
        self.info_frame = tk.Frame(main_content, bg=self.colors["bg"])
        self.info_frame.pack(fill="x", pady=(0, 20))

        self.contadores_labels = {}
        
        def crear_card_contador(
            parent,
            key,
            titulo,
            color_borde,
            side="left",
            pady=0,
            fixed_height=140,
            expand=True,
            value_font=None,
        ):
            card = tk.Frame(parent, bg=self.colors["card"])
            card.pack(side=side, fill="both", expand=expand, padx=10, pady=pady)
            if fixed_height:
                card.configure(height=fixed_height)
                card.pack_propagate(False)
            
            # Borde superior de color
            tk.Frame(card, bg=color_borde, height=4).pack(fill="x", side="top")
            
            content = tk.Frame(card, bg=self.colors["card"], padx=20, pady=14)
            content.pack(fill="both", expand=True)
            
            tk.Label(content, text=titulo.upper(), font=("Segoe UI", 10, "bold"), fg="#7F8C8D", bg=self.colors["card"]).pack(anchor="w")
            label_valor = tk.Label(
                content,
                text=str(self.contadores[key]),
                font=value_font or self.fonts["big"],
                fg=self.colors["text"],
                bg=self.colors["card"],
            )
            label_valor.pack(anchor="w", pady=(8, 0))
            
            self.contadores_labels[key] = label_valor

        crear_card_contador(self.info_frame, "fichas_restantes", "Fichas Restantes", self.colors["primary"], fixed_height=150)
        # crear_card_contador(self.info_frame, "fichas_expendidas", "Fichas Expendidas", self.colors["success"]) # Movido a Contadores

        # Arrancar refresco rápido una vez que el label grande ya existe.
        _refresh_fast_status()

        # --- Helper para Botones Redondeados ---
        def crear_boton_redondeado(parent, text, command, bg_color, fg_color, width=200, height=45, radius=20):
            canvas = tk.Canvas(parent, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0)
            
            def round_rect(x1, y1, x2, y2, r, **kwargs):
                points = (x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y1+r, x2, y2-r, x2, y2-r, x2, y2, x2-r, y2, x2-r, y2, x1+r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y2-r, x1, y1+r, x1, y1+r, x1, y1)
                return canvas.create_polygon(points, **kwargs, smooth=True)
                
            rect_id = round_rect(2, 2, width-2, height-2, radius, fill=bg_color, outline=bg_color)
            text_id = canvas.create_text(width/2, height/2, text=text, fill=fg_color, font=("Segoe UI", 11, "bold"))
            
            def on_click(e):
                if command: command()
            
            def on_enter(e):
                canvas.itemconfig(rect_id, fill="#34495E") # Color hover genérico
                
            def on_leave(e):
                canvas.itemconfig(rect_id, fill=bg_color)
                
            canvas.tag_bind(rect_id, "<Button-1>", on_click)
            canvas.tag_bind(text_id, "<Button-1>", on_click)
            canvas.bind("<Enter>", on_enter)
            canvas.bind("<Leave>", on_leave)
            
            return canvas

        # --- Sección de Acción ---
        self.botones_frame = tk.Frame(main_content, bg=self.colors["bg"])
        self.botones_frame.pack(fill="x")

        # Sección de Expendio Manual Integrada
        self.expender_frame = tk.Frame(self.botones_frame, bg=self.colors["card"])
        self.expender_frame.pack(fill="x", padx=10, pady=(0, 12))
        
        tk.Frame(self.expender_frame, bg=self.colors["warning"], height=4).pack(fill="x", side="top")
        
        expender_content = tk.Frame(self.expender_frame, bg=self.colors["card"], padx=20, pady=15)
        expender_content.pack(fill="both")

        tk.Label(expender_content, text="Expendio Manual", font=self.fonts["h2"], bg=self.colors["card"], fg=self.colors["warning"]).pack(anchor="w", pady=(0, 10))
        
        input_area = tk.Frame(expender_content, bg=self.colors["card"])
        input_area.pack(anchor="w")
        
        tk.Label(input_area, text="Cantidad de Fichas:", font=("Segoe UI", 12, "bold"), bg=self.colors["card"], fg="#7F8C8D").pack(side="left")
        self.entry_fichas = tk.Entry(input_area, font=("Segoe UI", 14), width=8, bd=0, bg="#F0F3F4", justify="center")
        self.entry_fichas.pack(side="left", padx=15)
        
        # Botón Expender Redondeado
        btn_expender = crear_boton_redondeado(input_area, "Expender Ahora", self.procesar_expender_fichas, self.colors["warning"], "white", width=180, height=40)
        btn_expender.pack(side="left", padx=10)
        tk.Label(
            input_area,
            text="Uso: venta normal.\nCarga fichas pendientes para entregar.",
            font=("Segoe UI", 9),
            bg=self.colors["card"],
            fg="#7F8C8D",
            justify="left",
        ).pack(side="left", padx=(14, 0))

        # Sección de Devolución de Fichas
        self.devolucion_frame = tk.Frame(self.botones_frame, bg=self.colors["card"])
        self.devolucion_frame.pack(fill="x", padx=10, pady=(0, 12))
        
        tk.Frame(self.devolucion_frame, bg="#9B59B6", height=4).pack(fill="x", side="top") # Color morado para distinguir
        
        devolucion_content = tk.Frame(self.devolucion_frame, bg=self.colors["card"], padx=20, pady=15)
        devolucion_content.pack(fill="both")

        tk.Label(devolucion_content, text="Devolución de Fichas", font=self.fonts["h2"], bg=self.colors["card"], fg="#9B59B6").pack(anchor="w", pady=(0, 10))
        
        input_area_dev = tk.Frame(devolucion_content, bg=self.colors["card"])
        input_area_dev.pack(anchor="w")
        
        tk.Label(input_area_dev, text="Cantidad a Devolver:", font=("Segoe UI", 12, "bold"), bg=self.colors["card"], fg="#7F8C8D").pack(side="left")
        self.entry_devolucion = tk.Entry(input_area_dev, font=("Segoe UI", 14), width=8, bd=0, bg="#F0F3F4", justify="center")
        self.entry_devolucion.pack(side="left", padx=15)
        
        # Botón Devolución Redondeado
        btn_devolucion = crear_boton_redondeado(input_area_dev, "Devolver Fichas", self.procesar_devolucion_fichas, "#9B59B6", "white", width=180, height=40)
        btn_devolucion.pack(side="left", padx=10)
        tk.Label(
            input_area_dev,
            text="Uso: reintegro al cliente.\nNo suma dinero ingresado.",
            font=("Segoe UI", 9),
            bg=self.colors["card"],
            fg="#7F8C8D",
            justify="left",
        ).pack(side="left", padx=(14, 0))

        # Sección de Cambio de Fichas 
        self.cambio_frame = tk.Frame(self.botones_frame, bg=self.colors["card"])
        self.cambio_frame.pack(fill="x", padx=10, pady=(0, 12))
        
        tk.Frame(self.cambio_frame, bg="#1ABC9C", height=4).pack(fill="x", side="top") # Color turquesa
        
        cambio_content = tk.Frame(self.cambio_frame, bg=self.colors["card"], padx=20, pady=15)
        cambio_content.pack(fill="both")

        tk.Label(cambio_content, text="Cambio de Fichas", font=self.fonts["h2"], bg=self.colors["card"], fg="#1ABC9C").pack(anchor="w", pady=(0, 10))
        
        input_area_cambio = tk.Frame(cambio_content, bg=self.colors["card"])
        input_area_cambio.pack(anchor="w")
        
        tk.Label(input_area_cambio, text="Cantidad de Cambio:", font=("Segoe UI", 12, "bold"), bg=self.colors["card"], fg="#7F8C8D").pack(side="left")
        self.entry_cambio = tk.Entry(input_area_cambio, font=("Segoe UI", 14), width=8, bd=0, bg="#F0F3F4", justify="center")
        self.entry_cambio.pack(side="left", padx=15)
        
        # Botón Cambio Redondeado
        btn_cambio = crear_boton_redondeado(input_area_cambio, "Cambio Fichas", self.procesar_cambio_fichas, "#1ABC9C", "white", width=180, height=40)
        btn_cambio.pack(side="left", padx=10)
        tk.Label(
            input_area_cambio,
            text="Uso: Cambio de fichas especiales. \no fichas adquiridas en Gruas",
            font=("Segoe UI", 9),
            bg=self.colors["card"],
            fg="#7F8C8D",
            justify="left",
        ).pack(side="left", padx=(14, 0))

        # Herramientas rápidas de simulación en Inicio (solo admin)
        if self.username == "admin":
            self.sim_inicio_frame = tk.Frame(self.botones_frame, bg=self.colors["card"])
            self.sim_inicio_frame.pack(fill="x", padx=10, pady=(0, 12))
            tk.Frame(self.sim_inicio_frame, bg=self.colors["primary"], height=4).pack(fill="x", side="top")

            sim_inicio_content = tk.Frame(self.sim_inicio_frame, bg=self.colors["card"], padx=20, pady=15)
            sim_inicio_content.pack(fill="both")
            tk.Label(
                sim_inicio_content,
                text="Simulación rápida (admin)",
                font=self.fonts["h2"],
                bg=self.colors["card"],
                fg=self.colors["primary"],
            ).pack(anchor="w", pady=(0, 10))

            crear_boton_redondeado(
                sim_inicio_content,
                "Simular salida de fichas",
                self.simular_salida_fichas,
                self.colors["primary"],
                "white",
                width=260,
                height=40,
            ).pack(anchor="w")

        # Página de Contadores
        self.contadores_page, contadores_content = self.crear_contenedor_scrollable(root)
        
        tk.Label(contadores_content, text="Contadores en Tiempo Real", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["text"]).pack(anchor="w", pady=(0, 30))

        self.contadores_frame = tk.Frame(contadores_content, bg=self.colors["bg"])
        self.contadores_frame.pack(fill="both", expand=True)

        # Contenedor principal dividido en dos columnas
        cols_container = tk.Frame(self.contadores_frame, bg=self.colors["bg"])
        cols_container.pack(fill="both", expand=True)

        # Columna Izquierda (General y Desglose)
        col_izq = tk.Frame(cols_container, bg=self.colors["bg"])
        col_izq.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Columna Derecha (Promociones)
        col_der = tk.Frame(cols_container, bg=self.colors["bg"])
        col_der.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # --- Contenido Columna Izquierda ---
        # Fila 1: Dinero
        row_dinero = tk.Frame(col_izq, bg=self.colors["bg"])
        row_dinero.pack(fill="x", pady=(0, 10))
        crear_card_contador(row_dinero, "dinero_ingresado", "Dinero Ingresado", self.colors["success"], fixed_height=132)
        crear_card_contador(row_dinero, "fichas_expendidas", "Fichas Expendidas", self.colors["success"], fixed_height=132)

        # Fila 2: Desglose Fichas (Normales y Promo)
        row_desglose1 = tk.Frame(col_izq, bg=self.colors["bg"])
        row_desglose1.pack(fill="x", pady=10)
        crear_card_contador(row_desglose1, "fichas_normales", "Fichas Vendidas", self.colors["warning"], fixed_height=132)
        crear_card_contador(row_desglose1, "fichas_promocion", "Fichas x Promo", self.colors["primary"], fixed_height=132)

        # Fila 3: Desglose Fichas (Devolución)
        row_desglose2 = tk.Frame(col_izq, bg=self.colors["bg"])
        row_desglose2.pack(fill="x", pady=10)
        crear_card_contador(row_desglose2, "fichas_devolucion", "Fichas Devueltas", "#9B59B6", fixed_height=132)
        crear_card_contador(row_desglose2, "fichas_cambio", "Fichas Cambio", "#1ABC9C", fixed_height=132)

        # --- Contenido Columna Derecha (Promociones en columna) ---
        tk.Label(col_der, text="Detalle Promociones", font=("Segoe UI", 12, "bold"), bg=self.colors["bg"], fg="#7F8C8D").pack(anchor="w", pady=(0, 10), padx=10)
        
        promo_counter_font = ("Segoe UI", 22, "bold")
        crear_card_contador(
            col_der,
            "promo1_contador",
            "Promo 1 Usadas",
            self.colors["primary"],
            side="top",
            pady=5,
            fixed_height=160,
            expand=False,
            value_font=promo_counter_font,
        )
        crear_card_contador(
            col_der,
            "promo2_contador",
            "Promo 2 Usadas",
            self.colors["primary"],
            side="top",
            pady=5,
            fixed_height=160,
            expand=False,
            value_font=promo_counter_font,
        )
        crear_card_contador(
            col_der,
            "promo3_contador",
            "Promo 3 Usadas",
            self.colors["primary"],
            side="top",
            pady=5,
            fixed_height=160,
            expand=False,
            value_font=promo_counter_font,
        )

        # Página de simulación
        self.simulacion_frame, sim_content = self.crear_contenedor_scrollable(root)
        
        tk.Label(sim_content, text="Simulación", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["primary"]).pack(anchor="w", pady=(0, 20))
        
        crear_boton_redondeado(sim_content, "Simular Billetero", self.simular_billetero, self.colors["primary"], "white", width=300).pack(pady=10)
        crear_boton_redondeado(sim_content, "Simular Barrera", self.simular_barrera, self.colors["warning"], "white", width=300).pack(pady=10)
        crear_boton_redondeado(sim_content, "Simular Entrega de Fichas", self.simular_entrega_fichas, self.colors["success"], "white", width=300).pack(pady=10)

        # Página de configuración
        self.config_frame, config_content = self.crear_contenedor_scrollable(root)
        
        tk.Label(config_content, text="Configuración", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["primary"]).pack(anchor="w", pady=(0, 20))
        
        for promo in ["Promo 1", "Promo 2", "Promo 3"]:
            crear_boton_redondeado(config_content, f"Configurar {promo}", lambda p=promo: self.configurar_promo(p), self.colors["primary"], "white", width=300).pack(pady=5)
        crear_boton_redondeado(
            config_content,
            "Configurar atajos promociones",
            self.configurar_atajos_promociones,
            self.colors["primary"],
            "white",
            width=300,
        ).pack(pady=5)
        crear_boton_redondeado(
            config_content,
            "Calibrar sensores de tolvas",
            self.configurar_calibracion_tolvas,
            self.colors["warning"],
            "white",
            width=300,
        ).pack(pady=5)
        crear_boton_redondeado(
            config_content,
            "Configurar gestor de red",
            self.configurar_gestor_red,
            "#16A085",
            "white",
            width=300,
        ).pack(pady=5)
        crear_boton_redondeado(config_content, "Configurar Valor de Ficha", self.configurar_valor_ficha, self.colors["primary"], "white", width=300).pack(pady=5)
        crear_boton_redondeado(config_content, "Configurar Codigo Hardware", self.configurar_device_id, self.colors["primary"], "white", width=300).pack(pady=5)
        crear_boton_redondeado(config_content, "Configurar DNI Admin", self.configurar_dni_admin, self.colors["primary"], "white", width=300).pack(pady=5)

        # Página de reportes y cierre del día
        self.reportes_frame, reportes_content = self.crear_contenedor_scrollable(root)
        self._frame_to_page = {
            self.main_frame: "main",
            self.contadores_page: "contadores",
            self.config_frame: "config",
            self.reportes_frame: "reportes",
            self.simulacion_frame: "simulacion",
        }
        
        tk.Label(reportes_content, text="Cierre y Reportes", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["danger"]).pack(anchor="w", pady=(0, 20))
        
        crear_boton_redondeado(reportes_content, "Realizar Cierre", self.realizar_cierre, self.colors["danger"], "white", width=300).pack(pady=5)
        if self.username == "admin":
            crear_boton_redondeado(
                reportes_content,
                "Ver reportes BD (admin)",
                self.abrir_reportes_admin,
                "#8E44AD",
                "white",
                width=300,
            ).pack(pady=5)

        # Footer
        self.footer_frame = tk.Frame(root, bg=self.colors["sidebar"], height=30)
        self.footer_frame.pack(side="bottom", fill="x")

        self.footer_label = tk.Label(self.footer_frame, text="", bg=self.colors["sidebar"], fg="#BDC3C7", font=("Segoe UI", 10))
        self.footer_label.pack(pady=5)

        # --- Toast update (abajo izquierda) ---
        self._repo_root = Path(__file__).resolve().parent
        self._update_toast = None
        self._update_toast_visible = False
        self._update_check_running = False
        self._update_snooze_until_ts = 0.0
        self._update_last_check_ts = 0.0
        self._update_last_remote_hash = None
        self._init_update_toast()

        self.actualizar_fecha_hora()

        # --- ATAJOS DE TECLADO ---
        trigger_action = self._trigger_action

        # --- Configuración Global (Root) ---

        # Navegación global básica (si el foco se pierde)
        self.root.bind('<Up>', lambda e: self.entry_fichas.focus_set())
        self.root.bind('<KP_Up>', lambda e: self.entry_fichas.focus_set())

        self.root.bind('<Down>', lambda e: self.entry_cambio.focus_set())
        self.root.bind('<KP_Down>', lambda e: self.entry_cambio.focus_set())

        # Selección de tolva con flechas laterales
        self.root.bind('<Left>', lambda e: trigger_action(self.seleccionar_tolva_anterior))
        self.root.bind('<Right>', lambda e: trigger_action(self.seleccionar_tolva_siguiente))
        self.root.bind('<KP_Left>', lambda e: trigger_action(self.seleccionar_tolva_anterior))
        self.root.bind('<KP_Right>', lambda e: trigger_action(self.seleccionar_tolva_siguiente))

        self.aplicar_atajos_promos_root()

        # --- Configuración de Inputs (Bloquear teclas especiales) ---
        def configurar_input_atajos(entry):
            """Configura los atajos para un Entry y bloquea escritura de caracteres especiales"""
            
            # Navegación entre inputs con flechas
            if entry == self.entry_fichas:
                entry.bind('<Down>', lambda e: trigger_action(self.entry_devolucion.focus_set))
                entry.bind('<KP_Down>', lambda e: trigger_action(self.entry_devolucion.focus_set))
            elif entry == self.entry_devolucion:
                entry.bind('<Up>', lambda e: trigger_action(self.entry_fichas.focus_set))
                entry.bind('<KP_Up>', lambda e: trigger_action(self.entry_fichas.focus_set))
                entry.bind('<Down>', lambda e: trigger_action(self.entry_cambio.focus_set))
                entry.bind('<KP_Down>', lambda e: trigger_action(self.entry_cambio.focus_set))
            elif entry == self.entry_cambio:
                entry.bind('<Up>', lambda e: trigger_action(self.entry_devolucion.focus_set))
                entry.bind('<KP_Up>', lambda e: trigger_action(self.entry_devolucion.focus_set))
                # Down en el último podría ir al primero o nada
                entry.bind('<Down>', lambda e: trigger_action(self.entry_fichas.focus_set)) # Loop al inicio

            # Promos (bloquea escritura y dispara acción según config admin)
            self.aplicar_atajos_promos_entry(entry)

            # Enter para confirmar (detectar qué campo está activo)
            def on_enter(event):
                if event.widget == self.entry_fichas:
                    self.procesar_expender_fichas()
                elif event.widget == self.entry_devolucion:
                    self.procesar_devolucion_fichas()
                elif event.widget == self.entry_cambio:
                    self.procesar_cambio_fichas()
                return "break"
            
            entry.bind('<Return>', on_enter)
            entry.bind('<KP_Enter>', on_enter)
            
            # IMPORTANTE: Permitir navegación lateral con flechas izquierda/derecha
            # (No bloquear estas para edición de texto)
            # Left y Right se dejan sin bind para que funcionen normalmente

        # Aplicar configuración a ambos inputs
        configurar_input_atajos(self.entry_fichas)
        configurar_input_atajos(self.entry_devolucion)
        configurar_input_atajos(self.entry_cambio)
        self._entries_operativos = [self.entry_fichas, self.entry_devolucion, self.entry_cambio]
        self.asegurar_apertura_automatica_del_dia()
        self.actualizar_tolvas_gui()
        self.actualizar_estado_operacion_ui()
        self.actualizar_estado_red_ui(
            {
                "level": "UNKNOWN",
                "message": "Inicializando red",
                "active_connection": "",
                "signal_percent": None,
            }
        )
        self.network_service.start(callback=self._on_network_status_changed)
        self._startup_kiosk_mapped = False

        def _on_root_mapped(_event=None):
            if self._startup_kiosk_mapped:
                return
            self._startup_kiosk_mapped = True
            self.root.after(30, lambda: self.mostrar_frame(self.main_frame))

        self.root.bind('<Map>', _on_root_mapped, add='+')

        self.mostrar_frame(self.main_frame)
        self.root.after(1, lambda: self.mostrar_frame(self.main_frame))
        self.root.after(220, lambda: self.mostrar_frame(self.main_frame))
        # Evita que el primer toque se consuma solo en tomar foco de ventana.
        self.root.after(120, lambda: self.root.focus_force())

        # Reiniciar el contador de sesión al iniciar la GUI
        shared_buffer.gui_to_core_queue.put({'type': 'reset_sesion'})
        print(f"[GUI] Sesión iniciada para usuario: {username}")

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

    def _init_update_toast(self):
        toast = tk.Frame(self.root, bg="#1F2A36", bd=0, relief="flat")
        toast.place_forget()

        title = tk.Label(
            toast,
            text="Actualización disponible",
            bg="#1F2A36",
            fg="white",
            font=("Segoe UI", 10, "bold"),
        )
        title.pack(anchor="w", padx=12, pady=(10, 2))

        subtitle = tk.Label(
            toast,
            text="Hay cambios nuevos. ¿Querés actualizar ahora?",
            bg="#1F2A36",
            fg="#D5DBDB",
            font=("Segoe UI", 9),
            wraplength=260,
            justify="left",
        )
        subtitle.pack(anchor="w", padx=12, pady=(0, 10))

        btn_row = tk.Frame(toast, bg="#1F2A36")
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        def _later():
            # “Luego”: ocultar y no molestar por 15 min
            self._update_snooze_until_ts = time.time() + (15 * 60)
            self._hide_update_toast()

        def _now():
            self._hide_update_toast()
            self._run_update_now()

        tk.Button(
            btn_row,
            text="Actualizar ahora",
            command=_now,
            bg="#2ECC71",
            fg="white",
            activebackground="#27AE60",
            activeforeground="white",
            bd=0,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        ).pack(side="left")
        tk.Button(
            btn_row,
            text="Luego",
            command=_later,
            bg="#566573",
            fg="white",
            activebackground="#4D5B66",
            activeforeground="white",
            bd=0,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        ).pack(side="left", padx=(8, 0))

        self._update_toast = toast

    def _show_update_toast(self):
        if not self._update_toast or self._update_toast_visible:
            return
        # Abajo izquierda con margen (por encima del footer)
        try:
            self._update_toast.place(x=14, rely=1.0, y=-(30 + 14), anchor="sw")
            self._update_toast.lift()
            self._update_toast_visible = True
        except Exception:
            pass

    def _hide_update_toast(self):
        if not self._update_toast or not self._update_toast_visible:
            return
        try:
            self._update_toast.place_forget()
        finally:
            self._update_toast_visible = False

    def _check_updates_async(self):
        if self._update_check_running:
            return
        if time.time() < self._update_snooze_until_ts:
            return
        self._update_check_running = True

        def _worker():
            try:
                cfg = self.config_repository.load()
                settings = cfg.get("updater", {}) if isinstance(cfg.get("updater", {}), dict) else {}
                remote = str(settings.get("remote", "origin"))
                branch = str(settings.get("branch", "main"))
                enabled = bool(settings.get("enabled", False))
                if not enabled:
                    return {"available": False}

                # fetch + compare hashes
                subprocess.run(
                    ["git", "fetch", remote, branch],
                    cwd=str(self._repo_root),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(self._repo_root), text=True).strip()
                remote_hash = subprocess.check_output(
                    ["git", "rev-parse", f"{remote}/{branch}"],
                    cwd=str(self._repo_root),
                    text=True,
                ).strip()
                return {"available": local != remote_hash, "remote_hash": remote_hash}
            except Exception:
                return {"available": False}

        def _done(result):
            try:
                self._update_last_remote_hash = result.get("remote_hash")
                if result.get("available"):
                    self._show_update_toast()
                else:
                    self._hide_update_toast()
            finally:
                self._update_check_running = False

        def _run_and_callback():
            res = _worker()
            self.root.after(0, lambda: _done(res))

        _threading.Thread(target=_run_and_callback, daemon=True).start()

    def _run_update_now(self):
        # Ejecuta updater y fuerza reinicio de la app (kiosk la vuelve a levantar)
        def _worker():
            try:
                cmd = [self._python_executable(), str(self._repo_root / "updater" / "auto_updater.py"), "--once"]
                subprocess.run(cmd, cwd=str(self._repo_root), check=False)
            except Exception as exc:
                print(f"[UPDATER UI] Error al actualizar: {exc}")
                return
            try:
                # Salir para que el launcher kiosk reinicie con el nuevo código
                self.root.after(0, self.root.destroy)
            except Exception:
                pass

        _threading.Thread(target=_worker, daemon=True).start()

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

        # En Raspberry touch a veces el primer cambio de vista queda "a medio render".
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

    def _normalizar_atajos_promociones(self, hotkeys_cfg):
        if not isinstance(hotkeys_cfg, dict):
            hotkeys_cfg = {}
        normalized = {}
        for promo, default_keys in DEFAULT_PROMO_HOTKEYS.items():
            raw = hotkeys_cfg.get(promo, default_keys)
            if isinstance(raw, str):
                raw = [raw]
            if not isinstance(raw, list):
                raw = list(default_keys)
            clean = []
            for key in raw:
                key_str = str(key).strip()
                if key_str and key_str not in clean:
                    clean.append(key_str)
            if not clean:
                clean = list(default_keys)
            normalized[promo] = clean
        return normalized

    def _actualizar_candidatos_atajos(self):
        candidates = set()
        for keys in DEFAULT_PROMO_HOTKEYS.values():
            candidates.update(keys)
        for keys in self.atajos_promociones.values():
            candidates.update(keys)
        self._promo_binding_candidates = candidates

    @staticmethod
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

    def aplicar_atajos_promos_root(self):
        self._actualizar_candidatos_atajos()
        for key in self._promo_binding_candidates:
            self.root.unbind(key)
        for promo, keys in self.atajos_promociones.items():
            for key in keys:
                self.root.bind(key, lambda e, promo_name=promo: self._trigger_action(lambda: self.simular_promo(promo_name)))

    def aplicar_atajos_promos_entry(self, entry):
        self._actualizar_candidatos_atajos()
        for key in self._promo_binding_candidates:
            entry.unbind(key)
        for promo, keys in self.atajos_promociones.items():
            for key in keys:
                entry.bind(key, lambda e, promo_name=promo: self._trigger_action(lambda: self.simular_promo(promo_name)))

    def sincronizar_desde_core(self):
        """
        Llamada por el core cuando cambian los contadores.
        SIEMPRE usa root.after() para ejecutar en el hilo de Tkinter.
        NUNCA llama _actualizar() directamente desde el hilo del motor
        (causaría TclError con update_idletasks y mataría el loop del motor).
        """
        if self._after_sincronizar_pendiente:
            return

        def _actualizar():
            self._after_sincronizar_pendiente = False
            self._ultimo_evento_core_ts = datetime.now()

            fichas_restantes_hw = shared_buffer.get_fichas_restantes()
            fichas_expendidas_hw = shared_buffer.get_fichas_expendidas()

            nuevo_total = self.inicio_fichas_expendidas + fichas_expendidas_hw

            if nuevo_total != self.contadores["fichas_expendidas"]:
                self.contadores["fichas_expendidas"] = nuevo_total
                self.contadores_apertura["fichas_expendidas"] = self.inicio_apertura_fichas + fichas_expendidas_hw
                self.contadores_parciales["fichas_expendidas"] = self.inicio_parcial_fichas + fichas_expendidas_hw
                if self._active_page in ("main", "contadores"):
                    self.actualizar_contadores_gui()
                self.guardar_configuracion()

            if fichas_restantes_hw != self.contadores["fichas_restantes"]:
                self.contadores["fichas_restantes"] = fichas_restantes_hw
                if self._active_page in ("main", "contadores"):
                    self.actualizar_contadores_gui()

            if self._active_page == "main":
                self.actualizar_tolvas_gui()

        try:
            self._after_sincronizar_pendiente = True
            self.root.after(0, _actualizar)
        except Exception as e:
            # Si root.after falla, liberar el flag y NO ejecutar nada en este hilo.
            # El motor loop NO debe ejecutar código de Tkinter directamente.
            self._after_sincronizar_pendiente = False
            print(f"[GUI] root.after falló (se ignora, motor no afectado): {e}")

    def seleccionar_tolva_siguiente(self):
        self.core.seleccionar_tolva_siguiente()
        self.actualizar_tolvas_gui()

    def seleccionar_tolva_anterior(self):
        self.core.seleccionar_tolva_anterior()
        self.actualizar_tolvas_gui()

    def mostrar_menu_tolva(self, tolva_id):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(
            label="Auto-calibrar tolva",
            command=lambda tid=tolva_id: self.iniciar_auto_calibracion_tolva_ui(tid),
        )
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

    def iniciar_auto_calibracion_tolva_ui(self, tolva_id):
        confirm = messagebox.askyesno(
            "Auto-calibración",
            f"Se va a auto-calibrar la tolva {tolva_id}.\n"
            "El sistema va a dispensar fichas de prueba, medir tiempos y guardar calibración.\n\n"
            "¿Continuar?",
        )
        if not confirm:
            return

        ok, msg = self.core.iniciar_auto_calibracion_tolva(tolva_id, samples=32)
        if not ok:
            messagebox.showwarning("Auto-calibración", msg)
            return
        self.actualizar_tolvas_gui()
        self._poll_auto_calibracion_ui()

    def _poll_auto_calibracion_ui(self):
        estado = self.core.obtener_estado_auto_calibracion()
        self.actualizar_tolvas_gui()
        if estado.get("running"):
            self._auto_calib_after_id = self.root.after(600, self._poll_auto_calibracion_ui)
            return
        self._auto_calib_after_id = None
        if estado.get("finished"):
            err = str(estado.get("error", "") or "").strip()
            result = estado.get("result", {}) if isinstance(estado.get("result"), dict) else {}
            if err:
                messagebox.showwarning("Auto-calibración", f"Finalizó con aviso: {err}")
            elif result:
                messagebox.showinfo(
                    "Auto-calibración",
                    "Calibración guardada correctamente:\n"
                    f"pulso_min_s={result.get('pulso_min_s')}\n"
                    f"pulso_max_s={result.get('pulso_max_s')}\n"
                    f"timeout_motor_s={result.get('timeout_motor_s')}\n"
                    f"muestras={result.get('samples')}",
                )
            self.guardar_configuracion(inmediato=True)

    def actualizar_tolvas_gui(self):
        estados = self.core.get_tolvas_status()
        if not estados:
            # Fallback defensivo: en algunos arranques de Raspberry el core puede
            # demorar en publicar estado de tolvas durante los primeros segundos.
            hoppers_cfg = self.maquina_hoppers if isinstance(self.maquina_hoppers, list) else []
            if not hoppers_cfg:
                return
            estados = []
            for idx, hopper in enumerate(hoppers_cfg, start=1):
                if not isinstance(hopper, dict):
                    continue
                estados.append(
                    {
                        "id": int(hopper.get("id", idx)),
                        "nombre": str(hopper.get("nombre", f"Tolva {idx}")),
                        "seleccionada": idx == 1,
                        "trabada": False,
                        "calibrando": False,
                        "calibracion_progreso": 0,
                    }
                )
            if not estados:
                return

        signature = tuple(
            (
                int(estado.get("id", 0)),
                str(estado.get("nombre", "")),
                bool(estado.get("seleccionada")),
                bool(estado.get("trabada")),
                bool(estado.get("calibrando")),
                int(estado.get("calibracion_progreso", 0) or 0),
            )
            for estado in estados
        )
        if signature == self._last_tolvas_signature:
            self.actualizar_estado_operacion_ui(estados_tolvas=estados)
            return

        for estado in estados:
            tolva_id = estado["id"]
            if tolva_id not in self.tolva_cards:
                card = tk.Frame(self.tolvas_cards_row, bg="#ECEFF1", bd=0, highlightthickness=2)
                card.pack(side="left", fill="both", expand=True, padx=10, pady=4)
                if self.username == "admin":
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

            if estado.get("calibrando"):
                bg_color = "#5DADE2"
                text_color = "white"
                progreso = int(estado.get("calibracion_progreso", 0))
                estado_text = f"CALIBRANDO {progreso}%"
                icon_color = "#D6EAF8"
                border_color = "#AED6F1"
            elif estado["trabada"] and estado["seleccionada"]:
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
            estados_tolvas = self.core.get_tolvas_status()

        seleccionada = next((t for t in estados_tolvas if t.get("seleccionada")), None) if estados_tolvas else None
        trabada = bool(seleccionada and seleccionada.get("trabada"))
        motor_activo = bool(shared_buffer.get_motor_activo())
        pendientes = int(shared_buffer.get_fichas_restantes())

        if motor_activo:
            self.status_motor_lbl.config(text="Motor: ON", bg="#2ECC71", fg="white")
        else:
            self.status_motor_lbl.config(text="Motor: OFF", bg="#ECF0F1", fg="#2C3E50")

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
            self.contadores["fichas_restantes"] = pendientes
            label = self.contadores_labels.get("fichas_restantes")
            if label is not None:
                label.config(text=f"{pendientes}")
        except Exception:
            pass
        if self._ultimo_evento_core_ts:
            self.status_last_event_lbl.config(text=f"Últ. evento: {self._ultimo_evento_core_ts.strftime('%H:%M:%S')}")

    def mostrar_alerta_motor_trabado(self, fichas_pendientes):
        """
        Muestra una alerta crítica cuando el motor se traba.
        Esta función es llamada automáticamente desde el core.
        """
        def _mostrar():
            mensaje = (f"⚠️ PRECAUCIÓN - MOTOR TRABADO ⚠️\n\n"
                       f"El motor lleva demasiado tiempo encendido sin dispensar.\n"
                       f"Por favor, verifique el mecanismo y libere la obstrucción.")
            
            # Mostrar alerta simple (OK) en lugar de pregunta
            messagebox.showwarning("⚠️ MOTOR TRABADO", mensaje)

            # Al cerrar el cartel (Aceptar), desbloquear el motor para continuar
            self.core.unlock_motor()
        
        try:
            self.root.after(0, _mostrar)
        except:
            _mostrar()

    def cargar_configuracion(self):
        config = self.config_repository.load()
        self.promociones = config.get("promociones", self.promociones)
        self.valor_ficha = config.get("valor_ficha", self.valor_ficha)
        self.device_id = config.get("device_id", self.device_id)
        self.codigo_hardware = config.get("maquina", {}).get("codigo_hardware", self.device_id)
        self.dni_admin = config.get("admin", {}).get("dni_admin", self.dni_admin)
        self.api_config = config.get("api", self.api_config)
        self.heartbeat_intervalo_s = config.get("heartbeat", {}).get("intervalo_s", self.heartbeat_intervalo_s)
        self.maquina_hoppers = config.get("maquina", {}).get("hoppers", self.maquina_hoppers)
        self.atajos_promociones = self._normalizar_atajos_promociones(config.get("atajos", {}).get("promociones", self.atajos_promociones))
        self.operacion_config = config.get("operacion", self.operacion_config)
        if not isinstance(self.operacion_config, dict):
            self.operacion_config = {"ultima_apertura_fecha": ""}
        self.network_manager_cfg = config.get("network_manager", self.network_manager_cfg)
        if not isinstance(self.network_manager_cfg, dict):
            self.network_manager_cfg = {
                "enabled": True,
                "check_interval_s": 8,
                "reconnect_after_failures": 3,
                "backend_timeout_s": 3.0,
                "internet_host": "8.8.8.8",
                "backend_url": "",
                "preferred_interface": "",
            }
        if not str(self.network_manager_cfg.get("backend_url", "")).strip():
            self.network_manager_cfg["backend_url"] = self._build_backend_probe_url()
        self.contadores = self.counter_service.ensure_schema(config.get("contadores", self.contadores))
        self.contadores_apertura = self.counter_service.ensure_schema(config.get("contadores_apertura", self.contadores_apertura))
        self.contadores_parciales = self.counter_service.ensure_schema(config.get("contadores_parciales", self.contadores_parciales))

    def guardar_configuracion(self, inmediato=False):
        """
        Guarda config.json con debounce: espera 1.5s de inactividad antes de escribir.
        Usar inmediato=True solo cuando sea estrictamente necesario (cierre, sesión).
        Evita escribir a disco en cada ficha dispensada (muy costoso en SD card).
        """
        if inmediato:
            self._escribir_config_ahora()
            return
        # Cancelar timer anterior y arrancar uno nuevo (debounce 1.5s)
        if self._guardar_config_timer is not None:
            self._guardar_config_timer.cancel()
        import threading as _t
        self._guardar_config_timer = _t.Timer(1.5, lambda: self.root.after(0, self._escribir_config_ahora))
        self._guardar_config_timer.daemon = True
        self._guardar_config_timer.start()

    def _escribir_config_ahora(self):
        """Escribe config.json al disco (siempre en el hilo de Tkinter)."""
        codigo_hardware = self.codigo_hardware or self.device_id
        existing = self.config_repository.load()
        base_config = dict(existing)
        base_config.update(
            {
                "promociones": self.promociones,
                "valor_ficha": self.valor_ficha,
                "device_id": codigo_hardware,
                "contadores": self.contadores,
                "contadores_apertura": self.contadores_apertura,
                "contadores_parciales": self.contadores_parciales,
                "api": self.api_config,
                "admin": {"dni_admin": self.dni_admin},
                "atajos": {"promociones": self._normalizar_atajos_promociones(self.atajos_promociones)},
                "maquina": {
                    "codigo_hardware": codigo_hardware,
                    "tipo_maquina": 1,
                    "hoppers": self.maquina_hoppers,
                },
                "heartbeat": {"intervalo_s": self.heartbeat_intervalo_s},
                "operacion": self.operacion_config,
                "network_manager": self.network_manager_cfg,
            }
        )
        self.config_repository.save(base_config)

    def _build_backend_probe_url(self):
        base_urls = self.api_config.get("base_urls", []) if isinstance(self.api_config, dict) else []
        if not isinstance(base_urls, list) or not base_urls:
            return "https://maquinasbonus.com/"
        base = str(base_urls[0]).rstrip("/")
        return f"{base}/"

    def _on_network_status_changed(self, status):
        if not isinstance(status, dict):
            return
        self._network_status_ui = status
        try:
            self.root.after(0, lambda: self.actualizar_estado_red_ui(status))
        except Exception as exc:
            print(f"[GUI] No se pudo actualizar estado de red: {exc}")

    def actualizar_estado_red_ui(self, status=None):
        if status is None:
            status = self._network_status_ui if isinstance(self._network_status_ui, dict) else {}
        level = str(status.get("level", "UNKNOWN")).upper()
        message = str(status.get("message", "") or "").strip()
        conn_name = str(status.get("active_connection", "") or "").strip()
        signal = status.get("signal_percent")
        signal_text = f" {int(signal)}%" if isinstance(signal, (int, float)) else ""
        conn_text = f" {conn_name}" if conn_name else ""
        label_text = f"Red: {level}{conn_text}{signal_text}"
        if message and not conn_name:
            label_text = f"Red: {level} ({message})"

        # En pantallas chicas (kiosk) acortar para que no se recorte:
        # priorizamos nivel + señal, luego nombre de conexión.
        max_len = 32
        if len(label_text) > max_len:
            compact = f"Red: {level}{signal_text}"
            if message and level in ("OFFLINE", "DEGRADED", "DISABLED") and len(compact) < (max_len - 3):
                compact = f"{compact} ({message})"
            label_text = compact[:max_len]

        if level == "ONLINE":
            bg, fg = "#27AE60", "white"
        elif level == "DEGRADED":
            bg, fg = "#F39C12", "white"
        elif level == "OFFLINE":
            bg, fg = "#C0392B", "white"
        elif level == "DISABLED":
            bg, fg = "#7F8C8D", "white"
        else:
            bg, fg = "#D6EAF8", "#1B4F72"
        self.status_network_lbl.config(text=label_text, bg=bg, fg=fg)

    def asegurar_apertura_automatica_del_dia(self):
        """
        Ejecuta apertura automática una sola vez por día al primer login.
        Evita depender de un botón manual y deja registro en backend.
        """
        hoy = datetime.now().strftime("%Y-%m-%d")
        ultima_apertura = str(self.operacion_config.get("ultima_apertura_fecha", "") or "").strip()
        if ultima_apertura == hoy:
            return

        print(f"[GUI] Primera sesión del día ({hoy}) -> apertura automática")
        self.cierre_realizado = False

        # Nuevo ciclo diario
        self.contadores_apertura = self.counter_service.default_counters()
        self.contadores_parciales = self.counter_service.default_counters()

        # Ajustar bases para mantener consistencia con contador hardware acumulado
        hw_actual = shared_buffer.get_fichas_expendidas()
        self.inicio_apertura_fichas = -hw_actual
        self.inicio_parcial_fichas = -hw_actual

        apertura_info = self.session_service.build_daily_close(
            self.device_id,
            self.contadores_apertura,
            event_type="apertura",
        )
        _post_en_hilo(DNS + urlCierresCloud, apertura_info, "Apertura automática remota")
        _post_en_hilo(DNSLocal + urlCierresLocal, apertura_info, "Apertura automática local")

        self.operacion_config["ultima_apertura_fecha"] = hoy
        self.actualizar_contadores_gui()
        self.guardar_configuracion(inmediato=True)

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
            estado_captura.config(text=f"Atajos de {promo} limpiados.", fg="#7F8C8D")

        def agregar_default(promo):
            current_hotkeys[promo] = list(DEFAULT_PROMO_HOTKEYS[promo])
            refresh_row(promo)
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
            self.guardar_configuracion(inmediato=True)
            config_window.destroy()
            messagebox.showinfo("Atajos", "Atajos de promociones guardados correctamente.")

        botones = tk.Frame(config_window, bg="#ffffff")
        botones.pack(fill="x", padx=16, pady=14)
        tk.Button(botones, text="Guardar", command=guardar_atajos, bg="#4CAF50", fg="white", font=("Arial", 11), bd=0).pack(side="left", padx=(0, 8))
        tk.Button(botones, text="Cancelar", command=config_window.destroy, bg="#D32F2F", fg="white", font=("Arial", 11), bd=0).pack(side="left")

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
        hoppers = self.maquina_hoppers if isinstance(self.maquina_hoppers, list) else []
        for idx, hopper in enumerate(hoppers[:3]):
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

                    hopper = self.maquina_hoppers[idx]
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
                    self.core.recargar_tolvas_desde_config()
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
        if self.username != "admin":
            messagebox.showerror("Permiso denegado", "Solo administrador puede configurar el gestor de red.")
            return

        config_window = tk.Toplevel(self.root)
        config_window.title("Configurar gestor de red")
        config_window.geometry("560x470")
        config_window.minsize(560, 470)
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

        content_frame = tk.Frame(config_window, bg="#ffffff")
        content_frame.pack(fill="both", expand=True, padx=16, pady=(14, 8))

        tk.Label(
            content_frame,
            text="Monitor en tiempo real + reconexión automática con NetworkManager (nmcli).",
            bg="#ffffff",
            fg="#7F8C8D",
            font=("Segoe UI", 10),
            justify="left",
        ).pack(anchor="w", pady=(0, 10))
        tk.Checkbutton(
            content_frame,
            text="Habilitar gestor de red",
            variable=enabled_var,
            bg="#ffffff",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        form = tk.Frame(content_frame, bg="#ffffff")
        form.pack(fill="x", pady=(0, 8))

        def add_row(label, variable):
            row = tk.Frame(form, bg="#ffffff")
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, width=26, anchor="w", bg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
            tk.Entry(row, textvariable=variable, font=("Segoe UI", 9), justify="left").pack(side="left", fill="x", expand=True)

        add_row("Intervalo de chequeo (s)", check_interval_var)
        add_row("Fallas antes de reconectar", retry_var)
        add_row("Timeout backend (s)", timeout_var)
        add_row("Host de prueba internet", internet_host_var)
        add_row("URL backend para healthcheck", backend_url_var)
        add_row("Interfaz preferida (ej: wlan0)", iface_var)

        tk.Label(
            content_frame,
            text="Tip: en Raspberry Pi usar interfaz preferida 'wlan0' o 'eth0'.",
            bg="#ffffff",
            fg="#7F8C8D",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        def guardar():
            try:
                new_cfg = {
                    "enabled": bool(enabled_var.get()),
                    "check_interval_s": max(2, int(float(check_interval_var.get()))),
                    "reconnect_after_failures": max(1, int(float(retry_var.get()))),
                    "backend_timeout_s": max(0.5, float(timeout_var.get())),
                    "internet_host": internet_host_var.get().strip() or "8.8.8.8",
                    "backend_url": backend_url_var.get().strip(),
                    "preferred_interface": iface_var.get().strip(),
                }
            except ValueError:
                messagebox.showerror("Error", "Revisá los valores numéricos del gestor de red.")
                return

            self.network_manager_cfg = new_cfg
            self.guardar_configuracion(inmediato=True)
            self.network_service.stop()
            self.network_service.start(callback=self._on_network_status_changed)
            config_window.destroy()
            messagebox.showinfo("Gestor de red", "Configuración guardada y monitor reiniciado.")

        btn_row = tk.Frame(config_window, bg="#ffffff")
        btn_row.pack(side="bottom", fill="x", padx=16, pady=(6, 12))
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

    def abrir_reportes_admin(self):
        if self.username != "admin":
            messagebox.showerror("Permiso denegado", "Solo administrador puede ver reportes de BD.")
            return

        panel = tk.Toplevel(self.root)
        panel.title("Reportes y cierres (BD)")
        panel.geometry("1180x640")
        panel.configure(bg="#ffffff")
        panel.transient(self.root)
        self._set_modal_grab(panel)

        toolbar = tk.Frame(panel, bg="#ffffff")
        toolbar.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(toolbar, text="ID dispositivo", bg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        device_var = tk.StringVar(value=self.device_id)
        tk.Entry(toolbar, textvariable=device_var, width=20, font=("Segoe UI", 9)).pack(side="left", padx=(6, 12))
        tk.Label(toolbar, text="Límite", bg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        limit_var = tk.StringVar(value="80")
        tk.Entry(toolbar, textvariable=limit_var, width=6, font=("Segoe UI", 9), justify="center").pack(side="left", padx=(6, 12))
        status_lbl = tk.Label(toolbar, text="", bg="#ffffff", fg="#7F8C8D", font=("Segoe UI", 9, "bold"))
        status_lbl.pack(side="left", padx=(8, 0))

        notebook = ttk.Notebook(panel)
        notebook.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        daily_tab = tk.Frame(notebook, bg="#ffffff")
        partial_tab = tk.Frame(notebook, bg="#ffffff")
        telemetry_tab = tk.Frame(notebook, bg="#ffffff")
        summary_tab = tk.Frame(notebook, bg="#ffffff")
        notebook.add(daily_tab, text="Cierres diarios")
        notebook.add(partial_tab, text="Cierres parciales")
        notebook.add(telemetry_tab, text="Telemetría expendedora")
        notebook.add(summary_tab, text="Resumen reportes")

        daily_cols = ("id_cierre", "id_dispositivo", "fichas_totales", "dinero", "p1", "p2", "p3", "fichas_promo", "fecha_apertura", "tipo_evento")
        partial_cols = (
            "id_cierre_parcial",
            "id_dispositivo",
            "id_cajero",
            "fichas_totales",
            "dinero",
            "p1",
            "p2",
            "p3",
            "fichas_promo",
            "fichas_devolucion",
            "fichas_cambio",
            "fecha_apertura_turno",
        )
        telemetry_cols = ("id_lectura", "id_dispositivo", "fichas", "dinero", "fecha_registro")
        daily_tree = ttk.Treeview(daily_tab, columns=daily_cols, show="headings")
        partial_tree = ttk.Treeview(partial_tab, columns=partial_cols, show="headings")
        telemetry_tree = ttk.Treeview(telemetry_tab, columns=telemetry_cols, show="headings")
        summary_text = tk.Text(
            summary_tab,
            bg="#F8F9F9",
            fg="#2C3E50",
            font=("Consolas", 10),
            wrap="word",
            bd=1,
            relief="solid",
            padx=10,
            pady=10,
        )
        summary_text.pack(fill="both", expand=True, padx=8, pady=8)
        summary_text.insert("1.0", "Cargando resumen...")
        summary_text.config(state="disabled")

        for tree, columns in ((daily_tree, daily_cols), (partial_tree, partial_cols), (telemetry_tree, telemetry_cols)):
            for col in columns:
                tree.heading(col, text=col)
                width = 120
                if "fecha" in col:
                    width = 170
                elif col in ("id_dispositivo", "tipo_evento"):
                    width = 150
                tree.column(col, width=width, anchor="center")
            vsb = ttk.Scrollbar(tree.master, orient="vertical", command=tree.yview)
            hsb = ttk.Scrollbar(tree.master, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tree.pack(fill="both", expand=True, side="top")
            vsb.pack(side="right", fill="y")
            hsb.pack(side="bottom", fill="x")

        def fill_tree(tree, rows, columns):
            tree.delete(*tree.get_children())
            for row in rows:
                values = [row.get(col, "") for col in columns]
                tree.insert("", "end", values=values)

        def to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def to_int(value):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0

        def render_summary(daily_rows, partial_rows, telemetry_rows):
            total_daily = len(daily_rows)
            total_partial = len(partial_rows)
            total_telemetry = len(telemetry_rows)

            total_dinero_daily = sum(to_float(r.get("dinero")) for r in daily_rows)
            total_fichas_daily = sum(to_int(r.get("fichas_totales")) for r in daily_rows)
            total_promo_daily = sum(to_int(r.get("fichas_promo")) for r in daily_rows)

            total_dinero_partial = sum(to_float(r.get("dinero")) for r in partial_rows)
            total_fichas_partial = sum(to_int(r.get("fichas_totales")) for r in partial_rows)
            total_devolucion_partial = sum(to_int(r.get("fichas_devolucion")) for r in partial_rows)
            total_cambio_partial = sum(to_int(r.get("fichas_cambio")) for r in partial_rows)
            total_fichas_telemetry = sum(to_int(r.get("fichas")) for r in telemetry_rows)
            total_dinero_telemetry = sum(to_float(r.get("dinero")) for r in telemetry_rows)

            avg_daily = (total_dinero_daily / total_daily) if total_daily else 0.0
            avg_partial = (total_dinero_partial / total_partial) if total_partial else 0.0

            lines = [
                "RESUMEN DE REPORTES",
                "",
                f"- Registros diarios cargados: {total_daily}",
                f"- Registros parciales cargados: {total_partial}",
                f"- Lecturas telemetría cargadas: {total_telemetry}",
                "",
                "CIERRES DIARIOS",
                f"- Dinero total: ${total_dinero_daily:.2f}",
                f"- Fichas totales: {total_fichas_daily}",
                f"- Fichas promo: {total_promo_daily}",
                f"- Promedio dinero por cierre: ${avg_daily:.2f}",
                "",
                "CIERRES PARCIALES",
                f"- Dinero total: ${total_dinero_partial:.2f}",
                f"- Fichas totales: {total_fichas_partial}",
                f"- Fichas devolución: {total_devolucion_partial}",
                f"- Fichas cambio: {total_cambio_partial}",
                f"- Promedio dinero por subcierre: ${avg_partial:.2f}",
                "",
                "TELEMETRÍA EXPENDEDORA",
                f"- Dinero total telemetría: ${total_dinero_telemetry:.2f}",
                f"- Fichas total telemetría: {total_fichas_telemetry}",
                "",
                f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ]

            summary_text.config(state="normal")
            summary_text.delete("1.0", tk.END)
            summary_text.insert("1.0", "\n".join(lines))
            summary_text.config(state="disabled")

        def cargar():
            status_lbl.config(text="Consultando BD...", fg="#1F618D")
            try:
                limit = int(float(limit_var.get()))
            except ValueError:
                messagebox.showerror("Filtro inválido", "El límite debe ser numérico.")
                return
            device = device_var.get().strip()

            def worker():
                try:
                    daily_rows = self.report_repository.fetch_daily_closures(limit=limit, device_id=device)
                    partial_rows = self.report_repository.fetch_partial_closures(limit=limit, device_id=device)
                    telemetry_rows = self.report_repository.fetch_expendedora_telemetry(limit=limit, device_id=device)
                    self.root.after(
                        0,
                        lambda: (
                            fill_tree(daily_tree, daily_rows, daily_cols),
                            fill_tree(partial_tree, partial_rows, partial_cols),
                            fill_tree(telemetry_tree, telemetry_rows, telemetry_cols),
                            render_summary(daily_rows, partial_rows, telemetry_rows),
                            status_lbl.config(
                                text=(
                                    f"{len(daily_rows)} diarios | {len(partial_rows)} parciales | "
                                    f"{len(telemetry_rows)} telemetría"
                                ),
                                fg="#1E8449",
                            ),
                        ),
                    )
                except Exception as exc:
                    err_text = format_db_exception(exc)
                    hint = (
                        " En config.json, sección \"mysql\": objetos \"local\" y \"production\" "
                        "(host, usuario, contraseña, database)."
                    )
                    self.root.after(
                        0,
                        lambda t=err_text, h=hint: status_lbl.config(
                            text=f"Error BD: {t}.{h}",
                            fg="#C0392B",
                        ),
                    )

            _threading.Thread(target=worker, daemon=True).start()

        tk.Button(toolbar, text="Refrescar", command=cargar, bg="#3498DB", fg="white", font=("Segoe UI", 9, "bold"), bd=0, padx=12, pady=4).pack(side="right")
        cargar()

    def configurar_promo(self, promo):
        config_window = tk.Toplevel(self.root)
        config_window.title(f"Configurar {promo}")
        config_window.geometry("300x250")
        config_window.configure(bg="#ffffff")
        
        tk.Label(config_window, text="Precio (en $):", bg="#ffffff", font=("Arial", 12)).pack(pady=10)
        precio_entry = tk.Entry(config_window, font=("Arial", 12), bd=2, relief="solid")
        precio_entry.insert(0, self.promociones[promo]["precio"])
        precio_entry.pack(pady=5, padx=10, fill='x')
        
        tk.Label(config_window, text="Fichas entregadas:", bg="#ffffff", font=("Arial", 12)).pack(pady=10)
        fichas_entry = tk.Entry(config_window, font=("Arial", 12), bd=2, relief="solid")
        fichas_entry.insert(0, self.promociones[promo]["fichas"])
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
            self.contadores_labels["fichas_restantes"].config(text=f"{current_fichas + cantidad_fichas}")

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
            self.contadores_labels["dinero_ingresado"].config(text=f"${self.contadores['dinero_ingresado']:.2f}")
            
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
            self.contadores_labels["fichas_restantes"].config(text=f"{current_fichas + cantidad_fichas}")

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

    def procesar_cambio_fichas(self):
        try:
            cantidad_str = self.entry_cambio.get()
            if not cantidad_str:
                self.entry_cambio.focus_set()
                return
            
            cantidad_fichas = int(cantidad_str)
            if cantidad_fichas <= 0:
                messagebox.showerror("Error", "La cantidad debe ser mayor a 0.")
                self.entry_cambio.focus_set()
                return

            # Actualización optimista
            current_fichas = self.contadores["fichas_restantes"]
            self.contadores_labels["fichas_restantes"].config(text=f"{current_fichas + cantidad_fichas}")

            shared_buffer.gui_to_core_queue.put({'type': 'add_fichas', 'cantidad': cantidad_fichas})

            # Actualizar contadores de cambio
            self.contadores["fichas_cambio"] += cantidad_fichas
            self.contadores_apertura["fichas_cambio"] += cantidad_fichas
            self.contadores_parciales["fichas_cambio"] += cantidad_fichas

            self.guardar_configuracion()
            
            if "fichas_cambio" in self.contadores_labels:
                self.contadores_labels["fichas_cambio"].config(text=f"{self.contadores['fichas_cambio']}")

            self.entry_cambio.delete(0, tk.END)
            self.entry_cambio.focus_set()
            
        except ValueError:
            messagebox.showerror("Error", "Ingrese un valor numérico válido.")
            self.entry_cambio.focus_set()

    def realizar_apertura(self):
        # Inicia la apertura del día
        self.contadores_apertura["device_id"] = self.device_id
        
        # Insertar cierre inicial con todo en 0 para registrar el día
        cierre_inicial = self.session_service.build_daily_close(
            self.device_id,
            self.contadores_apertura,
            event_type="apertura",
        )
        
        # Enviar cierre inicial al servidor remoto y local (no bloquea la GUI)
        _post_en_hilo(DNS + urlCierresCloud, cierre_inicial, "Apertura remota")
        _post_en_hilo(DNSLocal + urlCierresLocal, cierre_inicial, "Apertura local")

        self.operacion_config["ultima_apertura_fecha"] = datetime.now().strftime("%Y-%m-%d")
        
        self.actualizar_contadores_gui()
        self.guardar_configuracion(inmediato=True)
        messagebox.showinfo("Apertura", "Apertura del día realizada con éxito.\nRegistro inicial creado en el sistema.")

    def realizar_cierre(self):
        # Realiza el cierre del día
        cierre_info = self.session_service.build_daily_close(self.device_id, self.contadores_apertura)
        # Actualizamos el device_id en el diccionario existente en lugar de recrearlo
        self.contadores_apertura["device_id"] = self.device_id
        mensaje_cierre = (
            f"Fichas expendidas: {cierre_info['fichas_expendidas']}\n"
            f"Dinero ingresado: ${cierre_info['dinero_ingresado']:.2f}\n"
            f"Promo 1 usadas: {cierre_info['promo1_contador']}\n"
            f"Promo 2 usadas: {cierre_info['promo2_contador']}\n"
            f"Promo 3 usadas: {cierre_info['promo3_contador']}\n"
            f"--- Desglose ---\n"
            f"Vendidas: {cierre_info['fichas_normales']} | Promoción: {cierre_info['fichas_promocion']} | Devolución: {cierre_info['fichas_devolucion']} | Cambio: {cierre_info['fichas_cambio']}"
        )
        messagebox.showinfo("Cierre", f"Cierre del día realizado:\n{mensaje_cierre}")
        
        # Enviar datos al servidor (no bloquea la GUI)
        _post_en_hilo(DNS + urlCierresCloud, cierre_info, "Cierre remoto")
        _post_en_hilo(DNSLocal + urlCierresLocal, cierre_info, "Cierre local")
        
        # IMPORTANTE: Guardar los contadores parciales ANTES de resetear
        # para que el subcierre tenga los datos correctos
        self.contadores_parciales_pre_cierre = self.contadores_parciales.copy()
        
        self.contadores = self.counter_service.default_counters()
        self.contadores_apertura = self.counter_service.default_counters()
        self.contadores_parciales = self.counter_service.default_counters()
        
        # Ajustar bases para que coincidan con el reset (Base = 0 - HW_Actual)
        hw_actual = shared_buffer.get_fichas_expendidas()
        self.inicio_fichas_expendidas = -hw_actual
        self.inicio_apertura_fichas = -hw_actual
        self.inicio_parcial_fichas = -hw_actual
        
        # Marcar que se realizó un cierre para evitar doble reporte en cerrar_sesion
        self.cierre_realizado = True
        
        self.guardar_configuracion(inmediato=True)

    def realizar_cierre_parcial(self):
        # Realiza el cierre parcial
        subcierre_info = self.session_service.build_partial_close(
            self.device_id,
            self.contadores_parciales,
            self.username,
            cashier_id=self.cashier_id,
        )

        mensaje_subcierre = (
            f"Fichas expendidas: {subcierre_info['partial_fichas']}\n"
            f"Dinero ingresado: ${subcierre_info['partial_dinero']:.2f}\n"
            f"Promo 1 usadas: {subcierre_info['partial_p1']}\n"
            f"Promo 2 usadas: {subcierre_info['partial_p2']}\n"
            f"Promo 3 usadas: {subcierre_info['partial_p3']}\n"
            f"Devoluciones: {subcierre_info['partial_devolucion']}\n"
            f"Cambio: {subcierre_info['partial_cambio']}"
        )
        messagebox.showinfo("Cierre Parcial", f"Cierre parcial realizado:\n{mensaje_subcierre}")

        # Enviar datos al servidor (no bloquea la GUI)
        _post_en_hilo(
            DNS + urlSubcierreCloud,
            subcierre_info,
            "Subcierre remoto",
            retry_without_cashier_id=True,
        )
        _post_en_hilo(DNSLocal + urlSubcierreLocal, subcierre_info, "Subcierre local")

        # Reiniciar los contadores parciales
        self.contadores_parciales = self.counter_service.default_counters()
        
        # Ajustar base parcial
        hw_actual = shared_buffer.get_fichas_expendidas()
        self.inicio_parcial_fichas = -hw_actual
        
        self.guardar_configuracion(inmediato=True)

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
            self.network_service.stop()
        except Exception:
            pass
        self._cancel_after("_after_id")
        self._cancel_after("_after_fast_status_id")
        self._cancel_after("_auto_calib_after_id")
        self._after_sincronizar_pendiente = False
        if destroy_root:
            try:
                self.root.destroy()
            except Exception:
                pass

    def _on_window_close(self):
        self._shutdown_ui(destroy_root=True)

    def cerrar_sesion(self):
        try:
            # Determinar qué contadores usar para el subcierre
            # Si se hizo un cierre del día, usar los contadores guardados antes del cierre
            # Si NO se hizo cierre, usar los contadores parciales actuales
            if hasattr(self, 'cierre_realizado') and self.cierre_realizado:
                contadores_a_enviar = getattr(self, 'contadores_parciales_pre_cierre', {
                    "fichas_expendidas": 0,
                    "dinero_ingresado": 0,
                    "promo1_contador": 0,
                    "promo2_contador": 0,
                    "promo3_contador": 0,
                    "fichas_devolucion": 0,
                    "fichas_normales": 0,
                    "fichas_promocion": 0,
                    "fichas_cambio": 0
                })
                print("[GUI] Usando contadores pre-cierre para subcierre")
            else:
                contadores_a_enviar = self.contadores_parciales
                print("[GUI] Usando contadores parciales actuales para subcierre")

            # Best-effort: no bloquear logout si falla remoto/local.
            try:
                subcierre_info = self.session_service.build_partial_close(
                    self.device_id,
                    contadores_a_enviar,
                    self.username,
                    cashier_id=self.cashier_id,
                )
                _post_en_hilo(
                    DNS + urlSubcierreCloud,
                    subcierre_info,
                    "Cierre sesion remoto",
                    retry_without_cashier_id=True,
                )
                _post_en_hilo(DNSLocal + urlSubcierreLocal, subcierre_info, "Cierre sesion local")
            except Exception as exc:
                print(f"[GUI] Aviso: no se pudo generar/enviar subcierre en logout: {exc}")

            self.contadores = self.counter_service.default_counters()
            self.contadores_parciales = self.counter_service.default_counters()
            try:
                shared_buffer.reset_fichas_expendidas_sesion()
                shared_buffer.set_fichas_expendidas(0)
            except Exception as exc:
                print(f"[GUI] Aviso reseteando buffer de sesión: {exc}")
            try:
                self.actualizar_contadores_gui()
                self.guardar_configuracion(inmediato=True)
            except Exception as exc:
                print(f"[GUI] Aviso guardando estado de sesión: {exc}")

            messagebox.showinfo("Cerrar Sesión", "La sesión ha sido cerrada.")
        finally:
            if callable(self.on_logout):
                try:
                    self.on_logout()
                except Exception as exc:
                    print(f"[GUI] on_logout callback error: {exc}")
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

    def expender_fichas_gui(self):
        """Ya no es necesaria - el hardware controla todo automáticamente"""
        pass

    def simular_billetero(self):
        messagebox.showinfo("Simulación", "Billetero activado: Se ha ingresado dinero.")

    def simular_barrera(self):
        messagebox.showinfo("Simulación", "Barrera activada: Se detectó una ficha.")

    def simular_entrega_fichas(self):
        self.simular_salida_fichas()
        
    def simular_salida_fichas(self):
        """Simula una interrupción del sensor (BCM de la tolva seleccionada)."""
        try:
            self.core.simulate_sensor_pulse()
        except Exception as e:
            messagebox.showerror("Simulación", f"No se pudo simular el sensor:\n{e}")
            
    def simular_promo(self, promo):
        # Enviar comando al core via buffer compartido
        fichas = self.promociones[promo]["fichas"]
        promo_num = int(promo.split()[1])
        shared_buffer.gui_to_core_queue.put({'type': 'promo', 'promo_num': promo_num, 'fichas': fichas})

        # Aumentar el dinero ingresado según el precio de la promoción
        precio = self.promociones[promo]["precio"]
        self.contadores["dinero_ingresado"] += precio
        self.contadores_apertura["dinero_ingresado"] += precio
        self.contadores_parciales["dinero_ingresado"] += precio

        # Registrar fichas de promoción
        self.contadores["fichas_promocion"] += fichas
        self.contadores_apertura["fichas_promocion"] += fichas
        self.contadores_parciales["fichas_promocion"] += fichas

        self.contadores_labels["dinero_ingresado"].config(text=f"${self.contadores['dinero_ingresado']:.2f}")

        # **SOLUCIÓN**: Actualizar el buffer compartido para que el core lo vea
        shared_buffer.set_r_cuenta(self.contadores["dinero_ingresado"])

        # Diccionario para simular el switch
        promo_contadores = {
            "Promo 1": "promo1_contador",
            "Promo 2": "promo2_contador",
            "Promo 3": "promo3_contador"
        }

        # Incrementar el contador de la promoción correspondiente
        if promo in promo_contadores:
            self.contadores[promo_contadores[promo]] += 1
            self.contadores_apertura[promo_contadores[promo]] += 1
            self.contadores_parciales[promo_contadores[promo]] += 1
            # Estos labels fueron diseñados para mostrar solo el valor numérico.
            self.contadores_labels[promo_contadores[promo]].config(text=f"{self.contadores[promo_contadores[promo]]}")
        else:
            messagebox.showerror("Error", "Promoción no válida.")

        self.actualizar_contadores_gui()
        self.guardar_configuracion(inmediato=True)
        
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

if __name__ == "__main__":
    root = tk.Tk()
    app = ExpendedoraGUI(root, "username")  # Reemplazar "username" con el nombre de usuario actual

    root.mainloop()