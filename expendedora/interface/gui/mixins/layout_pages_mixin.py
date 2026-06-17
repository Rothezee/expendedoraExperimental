"""Mixin GUI: menú lateral y páginas principales."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class LayoutPagesMixin:
    def _build_layout_pages(self, root):
                # Menú lateral: navegación arriba + acción de cierre abajo (alineado con el footer).
                self.menu_frame = tk.Frame(root, width=250, bg=self.colors["sidebar"])
                self.menu_frame.pack(side="left", fill="y")
                self.menu_frame.pack_propagate(False)

                self.menu_nav_frame = tk.Frame(self.menu_frame, bg=self.colors["sidebar"])
                self.menu_nav_frame.pack(side="top", fill="both", expand=True)

                self.menu_bottom_frame = tk.Frame(self.menu_frame, bg=self.colors["sidebar"])
                self.menu_bottom_frame.pack(side="bottom", fill="x")

                tk.Label(
                    self.menu_nav_frame,
                    text="MENÚ PRINCIPAL",
                    bg=self.colors["sidebar"],
                    fg="#95A5A6",
                    font=("Segoe UI", 10, "bold"),
                ).pack(pady=(30, 10), padx=20, anchor="w")

                def crear_boton_menu(texto, comando, color_bg=self.colors["sidebar"], pady=1):
                    btn = tk.Button(
                        self.menu_nav_frame,
                        text=texto,
                        bg=color_bg,
                        fg="white",
                        font=self.fonts["body"],
                        bd=0,
                        activebackground="#34495E",
                        activeforeground="white",
                        command=comando,
                        anchor="w",
                        padx=20,
                        pady=10,
                        cursor="hand2",
                    )
                    btn.pack(fill="x", pady=pady)
                    return btn

                crear_boton_menu("Inicio", lambda: self.mostrar_frame(self.main_frame))
                crear_boton_menu("Contadores", lambda: self.mostrar_frame(self.contadores_page))
                crear_boton_menu("Red", self.configurar_gestor_red)
        
                if self._is_admin_user():
                    crear_boton_menu("Configuración", lambda: self.mostrar_frame(self.config_frame))
            
                crear_boton_menu("Cierre y Reportes", lambda: self.mostrar_frame(self.reportes_frame))
        
                if self._is_admin_user():
                    crear_boton_menu("Simulación", lambda: self.mostrar_frame(self.simulacion_frame))

                tk.Frame(self.menu_bottom_frame, bg="#243342", height=1).pack(fill="x")
                tk.Button(
                    self.menu_bottom_frame,
                    text="Cerrar Sesión",
                    bg=self.colors["danger"],
                    fg="white",
                    font=self.fonts["body"],
                    bd=0,
                    activebackground="#C0392B",
                    activeforeground="white",
                    command=self.cerrar_sesion,
                    anchor="w",
                    padx=20,
                    pady=12,
                    cursor="hand2",
                ).pack(fill="x", padx=12, pady=(10, 12))

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
                self._tolvas_section_title = tk.Label(
                    self.tolvas_frame,
                    text="Tolvas (← / → para seleccionar)",
                    font=("Segoe UI", 11, "bold"),
                    bg=self.colors["bg"],
                    fg="#7F8C8D",
                )
                self._tolvas_section_title.pack(anchor="w", padx=10, pady=(0, 6))
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
                self._start_fast_status_poll()

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

                    canvas.tag_bind(rect_id, "<Button-1>", on_click)
                    canvas.tag_bind(text_id, "<Button-1>", on_click)

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

                # Vaciar buffer de dispensado (revierte compra pendiente en caja)
                self.vaciar_buffer_frame = tk.Frame(self.botones_frame, bg=self.colors["card"])
                self.vaciar_buffer_frame.pack(fill="x", padx=10, pady=(0, 12))
                tk.Frame(self.vaciar_buffer_frame, bg="#95A5A6", height=4).pack(fill="x", side="top")
                vaciar_content = tk.Frame(self.vaciar_buffer_frame, bg=self.colors["card"], padx=20, pady=12)
                vaciar_content.pack(fill="both")
                tk.Label(
                    vaciar_content,
                    text="Operación especial",
                    font=("Segoe UI", 10, "bold"),
                    bg=self.colors["card"],
                    fg="#7F8C8D",
                ).pack(anchor="w", pady=(0, 6))
                crear_boton_redondeado(
                    vaciar_content,
                    "Vaciar fichas pendientes",
                    self.vaciar_buffer_dispensa_gui,
                    "#95A5A6",
                    "white",
                    width=220,
                    height=36,
                ).pack(anchor="w")
                tk.Label(
                    vaciar_content,
                    text="Anula la venta del buffer: revierte el dinero completo\n"
                    "y las fichas que ya salieron (devolvelas a la tolva antes).",
                    font=("Segoe UI", 9),
                    bg=self.colors["card"],
                    fg="#7F8C8D",
                    justify="left",
                ).pack(anchor="w", pady=(8, 0))

                # Herramientas rápidas de simulación en Inicio (solo admin)
                if self._is_admin_user():
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
                if self._is_admin_user():
                    crear_boton_redondeado(
                        reportes_content,
                        "Ver reportes BD (admin)",
                        self.abrir_reportes_admin,
                        "#8E44AD",
                        "white",
                        width=300,
                    ).pack(pady=5)

