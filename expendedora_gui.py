import tkinter as tk
from tkinter import messagebox
import json
import os
from datetime import datetime
import requests
from User_management import UserManagement
import expendedora_core as core
import shared_buffer

urlCierres = "esp32_project/expendedora/insert_close_expendedora.php"  # URL DE CIERRES
urlDatos = "esp32_project/expendedora/insert_data_expendedora.php"  # URL DE REPORTES
urlSubcierre = "esp32_project/expendedora/insert_subcierre_expendedora.php"  # URL DE SUBCIERRES
DNS = "https://maquinasbonus.com/"  # DNS servidor
DNSLocal = "http://127.0.0.1/"  # DNS servidor local

class ExpendedoraGUI:
    def __init__(self, root, username):
        self.root = root
        self.username = username
        self.root.title("Expendedora - Control") # El título no será visible
        self.root.attributes('-fullscreen', True) # Ocupa 100% de pantalla y oculta la barra de título
        self.root.configure(bg="#F4F7F6")

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
        self.promociones = {
            "Promo 1": {"precio": 0, "fichas": 0},
            "Promo 2": {"precio": 0, "fichas": 0},
            "Promo 3": {"precio": 0, "fichas": 0}
        }
        self.valor_ficha = 1.0
        self.device_id = ""

        # Contadores de la página principal
        self.contadores = {
            "fichas_expendidas": 0,
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }

        # Contadores de apertura
        self.contadores_apertura = {
            "fichas_expendidas": 0,
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }

        # Contadores parciales
        self.contadores_parciales = {
            "fichas_expendidas": 0,
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }


        # Flag para controlar si se realizó un cierre del día
        self.cierre_realizado = False
        self.contadores_parciales_pre_cierre = {}

        # Archivo de configuración
        self.config_file = "config.json"
        self.cargar_configuracion()

        # Registrar función de actualización con el core
        core.registrar_gui_actualizar(self.sincronizar_desde_core)
        shared_buffer.set_gui_update_callback(self.sincronizar_desde_core)

        # Header
        self.header_frame = tk.Frame(root, bg=self.colors["header"], height=60)
        self.header_frame.pack(side="top", fill="x")
        # Línea separadora
        tk.Frame(root, bg="#E0E0E0", height=1).pack(side="top", fill="x")

        tk.Label(self.header_frame, text="Expendedora Control", bg=self.colors["header"], fg=self.colors["text"], font=self.fonts["h2"]).pack(side="left", padx=20, pady=15)
        tk.Label(self.header_frame, text=f"Usuario: {username}", bg=self.colors["header"], fg=self.colors["text"], font=self.fonts["body"]).pack(side="right", padx=20)
        

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
        self.main_frame = tk.Frame(root, bg=self.colors["bg"])
        # Contenedor interno para padding
        main_content = tk.Frame(self.main_frame, bg=self.colors["bg"])
        main_content.pack(fill="both", expand=True, padx=30, pady=30)

        tk.Label(main_content, text="Panel de Control", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["text"]).pack(anchor="w", pady=(0, 20))

        # --- Cards de Fichas (Inicio) ---
        self.info_frame = tk.Frame(main_content, bg=self.colors["bg"])
        self.info_frame.pack(fill="x", pady=(0, 20))

        self.contadores_labels = {}
        
        def crear_card_contador(parent, key, titulo, color_borde, side="left", pady=0):
            card = tk.Frame(parent, bg=self.colors["card"])
            card.pack(side=side, fill="both", expand=True, padx=10, pady=pady)
            
            # Borde superior de color
            tk.Frame(card, bg=color_borde, height=4).pack(fill="x", side="top")
            
            content = tk.Frame(card, bg=self.colors["card"], padx=20, pady=20)
            content.pack(fill="both", expand=True)
            
            tk.Label(content, text=titulo.upper(), font=("Segoe UI", 10, "bold"), fg="#7F8C8D", bg=self.colors["card"]).pack(anchor="w")
            label_valor = tk.Label(content, text=str(self.contadores[key]), font=self.fonts["big"], fg=self.colors["text"], bg=self.colors["card"])
            label_valor.pack(anchor="w", pady=(5, 0))
            
            self.contadores_labels[key] = label_valor

        crear_card_contador(self.info_frame, "fichas_restantes", "Fichas Restantes", self.colors["primary"])
        crear_card_contador(self.info_frame, "fichas_expendidas", "Fichas Expendidas", self.colors["success"])

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
        self.botones_frame.pack(expand=True)

        # Sección de Expendio Manual Integrada
        self.expender_frame = tk.Frame(self.botones_frame, bg=self.colors["card"])
        self.expender_frame.pack(fill="x", pady=(0, 20))
        
        tk.Frame(self.expender_frame, bg=self.colors["warning"], height=4).pack(fill="x", side="top")
        
        expender_content = tk.Frame(self.expender_frame, bg=self.colors["card"], padx=20, pady=20)
        expender_content.pack(fill="both")

        tk.Label(expender_content, text="Expendio Manual", font=self.fonts["h2"], bg=self.colors["card"], fg=self.colors["warning"]).pack(anchor="w", pady=(0, 15))
        
        input_area = tk.Frame(expender_content, bg=self.colors["card"])
        input_area.pack(anchor="w")
        
        tk.Label(input_area, text="Cantidad de Fichas:", font=("Segoe UI", 12, "bold"), bg=self.colors["card"], fg="#7F8C8D").pack(side="left")
        self.entry_fichas = tk.Entry(input_area, font=("Segoe UI", 14), width=8, bd=0, bg="#F0F3F4", justify="center")
        self.entry_fichas.pack(side="left", padx=15)
        
        # Botón Expender Redondeado
        btn_expender = crear_boton_redondeado(input_area, "Expender Ahora", self.procesar_expender_fichas, self.colors["warning"], "white", width=180, height=40)
        btn_expender.pack(side="left", padx=10)

        # Sección de Devolución de Fichas (NUEVO)
        self.devolucion_frame = tk.Frame(self.botones_frame, bg=self.colors["card"])
        self.devolucion_frame.pack(fill="x", pady=(0, 20))
        
        tk.Frame(self.devolucion_frame, bg="#9B59B6", height=4).pack(fill="x", side="top") # Color morado para distinguir
        
        devolucion_content = tk.Frame(self.devolucion_frame, bg=self.colors["card"], padx=20, pady=20)
        devolucion_content.pack(fill="both")

        tk.Label(devolucion_content, text="Devolución de Fichas", font=self.fonts["h2"], bg=self.colors["card"], fg="#9B59B6").pack(anchor="w", pady=(0, 15))
        
        input_area_dev = tk.Frame(devolucion_content, bg=self.colors["card"])
        input_area_dev.pack(anchor="w")
        
        tk.Label(input_area_dev, text="Cantidad a Devolver:", font=("Segoe UI", 12, "bold"), bg=self.colors["card"], fg="#7F8C8D").pack(side="left")
        self.entry_devolucion = tk.Entry(input_area_dev, font=("Segoe UI", 14), width=8, bd=0, bg="#F0F3F4", justify="center")
        self.entry_devolucion.pack(side="left", padx=15)
        
        # Botón Devolución Redondeado
        btn_devolucion = crear_boton_redondeado(input_area_dev, "Devolver Fichas", self.procesar_devolucion_fichas, "#9B59B6", "white", width=180, height=40)
        btn_devolucion.pack(side="left", padx=10)

        # Botones de Promociones
        promos_container = tk.Frame(self.botones_frame, bg=self.colors["bg"])
        promos_container.pack(fill="x", pady=20)
        
        tk.Label(promos_container, text="Acciones Rápidas (Promociones)", font=("Segoe UI", 14, "bold"), bg=self.colors["bg"], fg=self.colors["primary"]).pack(anchor="w", pady=(0, 10))
        
        promos_grid = tk.Frame(promos_container, bg=self.colors["bg"])
        promos_grid.pack(fill="x")
        
        # Usar botones redondeados para promos
        p1 = crear_boton_redondeado(promos_grid, "Simular Promo 1", lambda: self.simular_promo("Promo 1"), self.colors["primary"], "white", width=200)
        p1.pack(side="left", padx=(0, 10))
        
        p2 = crear_boton_redondeado(promos_grid, "Simular Promo 2", lambda: self.simular_promo("Promo 2"), self.colors["primary"], "white", width=200)
        p2.pack(side="left", padx=10)
        
        p3 = crear_boton_redondeado(promos_grid, "Simular Promo 3", lambda: self.simular_promo("Promo 3"), self.colors["primary"], "white", width=200)
        p3.pack(side="left", padx=10)

        # Página de Contadores
        self.contadores_page = tk.Frame(root, bg=self.colors["bg"])
        contadores_content = tk.Frame(self.contadores_page, bg=self.colors["bg"])
        contadores_content.pack(fill="both", expand=True, padx=30, pady=30)
        
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
        crear_card_contador(row_dinero, "dinero_ingresado", "Dinero Ingresado", self.colors["success"])

        # Fila 2: Desglose Fichas (Normales y Promo)
        row_desglose1 = tk.Frame(col_izq, bg=self.colors["bg"])
        row_desglose1.pack(fill="x", pady=10)
        crear_card_contador(row_desglose1, "fichas_normales", "Fichas Vendidas", self.colors["warning"])
        crear_card_contador(row_desglose1, "fichas_promocion", "Fichas x Promo", self.colors["primary"])

        # Fila 3: Desglose Fichas (Devolución)
        row_desglose2 = tk.Frame(col_izq, bg=self.colors["bg"])
        row_desglose2.pack(fill="x", pady=10)
        crear_card_contador(row_desglose2, "fichas_devolucion", "Fichas Devueltas", "#9B59B6")
        tk.Frame(row_desglose2, bg=self.colors["bg"]).pack(side="left", fill="both", expand=True, padx=10) # Spacer

        # --- Contenido Columna Derecha (Promociones en columna) ---
        tk.Label(col_der, text="Detalle Promociones", font=("Segoe UI", 12, "bold"), bg=self.colors["bg"], fg="#7F8C8D").pack(anchor="w", pady=(0, 10), padx=10)
        
        crear_card_contador(col_der, "promo1_contador", "Promo 1 Usadas", self.colors["primary"], side="top", pady=5)
        crear_card_contador(col_der, "promo2_contador", "Promo 2 Usadas", self.colors["primary"], side="top", pady=5)
        crear_card_contador(col_der, "promo3_contador", "Promo 3 Usadas", self.colors["primary"], side="top", pady=5)

        # Página de simulación
        self.simulacion_frame = tk.Frame(root, bg=self.colors["bg"])
        sim_content = tk.Frame(self.simulacion_frame, bg=self.colors["bg"])
        sim_content.pack(fill="both", expand=True, padx=30, pady=30)
        
        tk.Label(sim_content, text="Simulación", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["primary"]).pack(anchor="w", pady=(0, 20))
        
        crear_boton_redondeado(sim_content, "Simular Billetero", self.simular_billetero, self.colors["primary"], "white", width=300).pack(pady=10)
        crear_boton_redondeado(sim_content, "Simular Barrera", self.simular_barrera, self.colors["warning"], "white", width=300).pack(pady=10)
        crear_boton_redondeado(sim_content, "Simular Entrega de Fichas", self.simular_entrega_fichas, self.colors["success"], "white", width=300).pack(pady=10)

        # Página de configuración
        self.config_frame = tk.Frame(root, bg=self.colors["bg"])
        config_content = tk.Frame(self.config_frame, bg=self.colors["bg"])
        config_content.pack(fill="both", expand=True, padx=30, pady=30)
        
        tk.Label(config_content, text="Configuración", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["primary"]).pack(anchor="w", pady=(0, 20))
        
        for promo in ["Promo 1", "Promo 2", "Promo 3"]:
            crear_boton_redondeado(config_content, f"Configurar {promo}", lambda p=promo: self.configurar_promo(p), self.colors["primary"], "white", width=300).pack(pady=5)
        crear_boton_redondeado(config_content, "Configurar Valor de Ficha", self.configurar_valor_ficha, self.colors["primary"], "white", width=300).pack(pady=5)
        crear_boton_redondeado(config_content, "Configurar ID Dispositivo", self.configurar_device_id, self.colors["primary"], "white", width=300).pack(pady=5)

        # Página de reportes y cierre del día
        self.reportes_frame = tk.Frame(root, bg=self.colors["bg"])
        reportes_content = tk.Frame(self.reportes_frame, bg=self.colors["bg"])
        reportes_content.pack(fill="both", expand=True, padx=30, pady=30)
        
        tk.Label(reportes_content, text="Cierre y Reportes", font=self.fonts["h1"], bg=self.colors["bg"], fg=self.colors["danger"]).pack(anchor="w", pady=(0, 20))
        
        crear_boton_redondeado(reportes_content, "Realizar Apertura", self.realizar_apertura, self.colors["primary"], "white", width=300).pack(pady=5)
        crear_boton_redondeado(reportes_content, "Realizar Cierre", self.realizar_cierre, self.colors["danger"], "white", width=300).pack(pady=5)

        # Footer
        self.footer_frame = tk.Frame(root, bg=self.colors["sidebar"], height=30)
        self.footer_frame.pack(side="bottom", fill="x")

        self.footer_label = tk.Label(self.footer_frame, text="", bg=self.colors["sidebar"], fg="#BDC3C7", font=("Segoe UI", 10))
        self.footer_label.pack(pady=5)

        self.actualizar_fecha_hora()

        # --- ATAJOS DE TECLADO ---
        def trigger_input(func):
            func()
            return "break"

        # --- NUEVOS ATAJOS (Teclado Numérico) ---
        # / (Dividir) -> Promo 1
        self.root.bind('<slash>', lambda e: self.simular_promo("Promo 1"))
        self.root.bind('<KP_Divide>', lambda e: self.simular_promo("Promo 1"))

        # * (Multiplicar) -> Promo 2
        self.root.bind('<asterisk>', lambda e: self.simular_promo("Promo 2"))
        self.root.bind('<KP_Multiply>', lambda e: self.simular_promo("Promo 2"))

        # - (Restar) -> Promo 3
        self.root.bind('<minus>', lambda e: self.simular_promo("Promo 3"))
        self.root.bind('<KP_Subtract>', lambda e: self.simular_promo("Promo 3"))

        # + (Sumar) -> Expender
        self.root.bind('<plus>', lambda e: self.procesar_expender_fichas())
        self.root.bind('<KP_Add>', lambda e: self.procesar_expender_fichas())

        # . (Punto) -> Devolución
        self.root.bind('<period>', lambda e: self.procesar_devolucion_fichas())
        self.root.bind('<KP_Decimal>', lambda e: self.procesar_devolucion_fichas())
        self.root.bind('<KP_Separator>', lambda e: self.procesar_devolucion_fichas())
        self.root.bind('<comma>', lambda e: self.procesar_devolucion_fichas())

        # --- Configuración de Inputs (Evitar escritura de teclas de acción) ---
        self.entry_fichas.bind('<Return>', lambda e: self.procesar_expender_fichas())
        self.entry_fichas.bind('<KP_Enter>', lambda e: self.procesar_expender_fichas())
        self.entry_fichas.bind('<KP_Add>', lambda e: trigger_input(self.procesar_expender_fichas))
        self.entry_fichas.bind('<plus>', lambda e: trigger_input(self.procesar_expender_fichas))
        # Navegación cruzada: Ir a Devolución con . desde Fichas
        self.entry_fichas.bind('<KP_Decimal>', lambda e: trigger_input(self.procesar_devolucion_fichas))
        self.entry_fichas.bind('<period>', lambda e: trigger_input(self.procesar_devolucion_fichas))
        self.entry_fichas.bind('<KP_Separator>', lambda e: trigger_input(self.procesar_devolucion_fichas))
        self.entry_fichas.bind('<comma>', lambda e: trigger_input(self.procesar_devolucion_fichas))



        # Promos desde Fichas (Evitar escritura)
        self.entry_fichas.bind('<slash>', lambda e: trigger_input(lambda: self.simular_promo("Promo 1")))
        self.entry_fichas.bind('<KP_Divide>', lambda e: trigger_input(lambda: self.simular_promo("Promo 1")))
        self.entry_fichas.bind('<asterisk>', lambda e: trigger_input(lambda: self.simular_promo("Promo 2")))
        self.entry_fichas.bind('<KP_Multiply>', lambda e: trigger_input(lambda: self.simular_promo("Promo 2")))
        self.entry_fichas.bind('<minus>', lambda e: trigger_input(lambda: self.simular_promo("Promo 3")))
        self.entry_fichas.bind('<KP_Subtract>', lambda e: trigger_input(lambda: self.simular_promo("Promo 3")))

        self.entry_devolucion.bind('<Return>', lambda e: self.procesar_devolucion_fichas())
  
        self.entry_devolucion.bind('<KP_Enter>', lambda e: self.procesar_devolucion_fichas())
        self.entry_devolucion.bind('<KP_Decimal>', lambda e: trigger_input(self.procesar_devolucion_fichas))
        self.entry_devolucion.bind('<period>', lambda e: trigger_input(self.procesar_devolucion_fichas))
        self.entry_devolucion.bind('<KP_Separator>', lambda e: trigger_input(self.procesar_devolucion_fichas))
        self.entry_devolucion.bind('<comma>', lambda e: trigger_input(self.procesar_devolucion_fichas))
        # Navegación cruzada: Ir a Expender con + desde Devolución
        self.entry_devolucion.bind('<KP_Add>', lambda e: trigger_input(self.procesar_expender_fichas))
        self.entry_devolucion.bind('<plus>', lambda e: trigger_input(self.procesar_expender_fichas))

        # Promos desde Devolución (Evitar escritura)
        self.entry_devolucion.bind('<slash>', lambda e: trigger_input(lambda: self.simular_promo("Promo 1")))
        self.entry_devolucion.bind('<KP_Divide>', lambda e: trigger_input(lambda: self.simular_promo("Promo 1")))
        self.entry_devolucion.bind('<asterisk>', lambda e: trigger_input(lambda: self.simular_promo("Promo 2")))
        self.entry_devolucion.bind('<KP_Multiply>', lambda e: trigger_input(lambda: self.simular_promo("Promo 2")))
        self.entry_devolucion.bind('<minus>', lambda e: trigger_input(lambda: self.simular_promo("Promo 3")))
        self.entry_devolucion.bind('<KP_Subtract>', lambda e: trigger_input(lambda: self.simular_promo("Promo 3")))

        self.mostrar_frame(self.main_frame)

        # Reiniciar el contador de sesión al iniciar la GUI
        shared_buffer.gui_to_core_queue.put({'type': 'reset_sesion'})
        print(f"[GUI] Sesión iniciada para usuario: {username}")

    #def enviar_datos_al_servidor(self):
    #    datos = {
    #        "device_id": "EXPENDEDORA_1",
    #        "dato1": self.contadores['fichas_expendidas'],
    #        "dato2": self.contadores['dinero_ingresado'],
    #    }

    #    try:
    #        response = requests.post(urlDatos, json=datos)
    #        if response.status_code == 200:
    #            print("Datos enviados con éxito")
    #        else:
    #            print(f"Error al enviar datos: {response.status_code}")
    #    except requests.exceptions.RequestException as e:
    #        print(f"Error al conectar con el servidor: {e}")

    def mostrar_frame(self, frame):
        for f in [self.main_frame, self.contadores_page, self.config_frame, self.reportes_frame, self.simulacion_frame]:
            f.pack_forget()
        frame.pack(fill="both", expand=True)

    def sincronizar_desde_core(self):
        """
        Llamada por el core cuando cambian los contadores.
        Lee directamente los valores actuales y actualiza la GUI.
        Se ejecuta en el hilo del core, usa root.after() para thread-safety.
        """
        def _actualizar():
            # Leer valores actuales del core (thread-safe)
            fichas_restantes_hw = shared_buffer.get_fichas_restantes()
            fichas_expendidas_hw = shared_buffer.get_fichas_expendidas()

            # 1. Sincronizar fichas expendidas si han aumentado
            diferencia_expendidas = fichas_expendidas_hw - self.contadores["fichas_expendidas"]
            if diferencia_expendidas > 0:
                self.contadores["fichas_expendidas"] = fichas_expendidas_hw
                self.contadores_apertura["fichas_expendidas"] += diferencia_expendidas
                self.contadores_parciales["fichas_expendidas"] += diferencia_expendidas
                # print(f"[GUI] ✓ FICHAS EXPENDIDAS | Total: {fichas_expendidas_hw} | +{diferencia_expendidas}")
                self.actualizar_contadores_gui()

            # 2. Sincronizar fichas restantes si han cambiado (independientemente de las expendidas)
            #    Esto cubre tanto la adición de fichas como el decremento al expender.
            if fichas_restantes_hw != self.contadores["fichas_restantes"]:
                self.contadores["fichas_restantes"] = fichas_restantes_hw
                # print(f"[GUI] ✓ FICHAS RESTANTES | Nuevo valor: {fichas_restantes_hw}")
                self.actualizar_contadores_gui()

        # Programar actualización en el hilo de Tkinter
        try:
            self.root.after(0, _actualizar)
        except:
            # Si after() no funciona, ejecutar directamente
            _actualizar()

    def cargar_configuracion(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.promociones = config.get("promociones", self.promociones)
                self.valor_ficha = config.get("valor_ficha", self.valor_ficha)
                self.device_id = config.get("device_id", self.device_id)
                
                # Cargar contadores, pero no reiniciar los de la sesión actual aquí
                self.contadores = config.get("contadores", self.contadores)
                self.contadores_apertura = config.get("contadores_apertura", self.contadores_apertura)
                self.contadores_parciales = config.get("contadores_parciales", self.contadores_parciales)

                # Asegurar que existan las nuevas claves (migración de config vieja)
                for d in [self.contadores, self.contadores_apertura, self.contadores_parciales]:
                    for key in ["fichas_devolucion", "fichas_normales", "fichas_promocion"]:
                        if key not in d:
                            d[key] = 0
        else:
            self.guardar_configuracion()

    def guardar_configuracion(self):
        config = {
            "promociones": self.promociones,
            "valor_ficha": self.valor_ficha,
            "device_id": self.device_id,
            "contadores": self.contadores,
            "contadores_apertura": self.contadores_apertura,
            "contadores_parciales": self.contadores_parciales
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=4)

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
                self.guardar_configuracion()
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
                self.guardar_configuracion()
                config_window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Ingrese un valor numérico válido.")
        
        tk.Button(config_window, text="Guardar", command=guardar_valor_ficha, bg="#4CAF50", fg="white", font=("Arial", 12), bd=0).pack(pady=5)
        tk.Button(config_window, text="Cancelar", command=config_window.destroy, bg="#D32F2F", fg="white", font=("Arial", 12), bd=0).pack(pady=5)

    def configurar_device_id(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configurar ID Dispositivo")
        config_window.geometry("300x150")
        config_window.configure(bg="#ffffff")
        
        tk.Label(config_window, text="ID del Dispositivo:", bg="#ffffff", font=("Arial", 12)).pack(pady=10)
        id_entry = tk.Entry(config_window, font=("Arial", 12), bd=2, relief="solid")
        id_entry.insert(0, self.device_id)
        id_entry.pack(pady=5, padx=10, fill='x')
        
        def guardar_id():
            new_id = id_entry.get().strip()
            if new_id:
                self.device_id = new_id
                self.guardar_configuracion()
                config_window.destroy()
            else:
                messagebox.showerror("Error", "El ID no puede estar vacío.")
        
        tk.Button(config_window, text="Guardar", command=guardar_id, bg="#4CAF50", fg="white", font=("Arial", 12), bd=0).pack(pady=5)
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
                return

            # **SOLUCIÓN MEJORADA**:
            # 1. Actualiza la GUI de forma optimista para una respuesta instantánea.
            #    El valor real se sincronizará desde el core en milisegundos.
            current_fichas = self.contadores["fichas_restantes"]
            self.contadores_labels["fichas_restantes"].config(text=f"Fichas Restantes: {current_fichas + cantidad_fichas}")

            # Enviar comando al core via buffer compartido
            shared_buffer.gui_to_core_queue.put({'type': 'add_fichas', 'cantidad': cantidad_fichas})
            # print(f"[GUI] Comando add_fichas enviado: {cantidad_fichas}")

            # Actualizar solo el dinero ingresado, NO fichas_restantes aquí
            dinero = cantidad_fichas * self.valor_ficha
            self.contadores["dinero_ingresado"] += dinero
            self.contadores_apertura["dinero_ingresado"] += dinero
            self.contadores_parciales["dinero_ingresado"] += dinero

            # Registrar como fichas normales (vendidas)
            self.contadores["fichas_normales"] += cantidad_fichas
            self.contadores_apertura["fichas_normales"] += cantidad_fichas
            self.contadores_parciales["fichas_normales"] += cantidad_fichas

            # **SOLUCIÓN**: Actualizar el buffer compartido para que el core lo vea
            shared_buffer.set_r_cuenta(self.contadores["dinero_ingresado"])

            self.guardar_configuracion()
            # Ya no llamamos a self.actualizar_contadores_gui() para todo,
            # solo actualizamos el dinero y las fichas restantes visualmente.
            self.contadores_labels["dinero_ingresado"].config(text=f"Dinero Ingresado: ${self.contadores['dinero_ingresado']:.2f}")
            
            # Limpiar el campo de entrada
            self.entry_fichas.delete(0, tk.END)
            self.root.focus()
            
        except ValueError:
            messagebox.showerror("Error", "Ingrese un valor numérico válido.")

    def procesar_devolucion_fichas(self):
        try:
            cantidad_str = self.entry_devolucion.get()
            if not cantidad_str:
                self.entry_devolucion.focus_set()
                return
            
            cantidad_fichas = int(cantidad_str)
            if cantidad_fichas <= 0:
                messagebox.showerror("Error", "La cantidad debe ser mayor a 0.")
                return

            # Actualización optimista de la GUI
            current_fichas = self.contadores["fichas_restantes"]
            self.contadores_labels["fichas_restantes"].config(text=f"Fichas Restantes: {current_fichas + cantidad_fichas}")

            # Enviar comando al core via buffer compartido
            shared_buffer.gui_to_core_queue.put({'type': 'add_fichas', 'cantidad': cantidad_fichas})

            # Actualizar contadores de devolución (SIN sumar dinero)
            self.contadores["fichas_devolucion"] += cantidad_fichas
            self.contadores_apertura["fichas_devolucion"] += cantidad_fichas
            self.contadores_parciales["fichas_devolucion"] += cantidad_fichas

            self.guardar_configuracion()
            
            # Actualizar etiqueta si existe
            if "fichas_devolucion" in self.contadores_labels:
                 self.contadores_labels["fichas_devolucion"].config(text=f"{self.contadores['fichas_devolucion']}")

            # Limpiar el campo de entrada
            self.entry_devolucion.delete(0, tk.END)
            self.root.focus()
            messagebox.showinfo("Devolución", f"Se han agregado {cantidad_fichas} fichas de devolución.")
            
        except ValueError:
            messagebox.showerror("Error", "Ingrese un valor numérico válido.")

    def realizar_apertura(self):
        # Inicia la apertura del día
        self.contadores_apertura = {
            "device_id": self.device_id,
            "fichas_expendidas": self.contadores_apertura['fichas_expendidas'],
            "dinero_ingresado": self.contadores_apertura['dinero_ingresado'],
            "promo1_contador": self.contadores_apertura['promo1_contador'],
            "promo2_contador": self.contadores_apertura['promo2_contador'],
            "promo3_contador": self.contadores_apertura['promo3_contador'],
            "fichas_devolucion": self.contadores_apertura['fichas_devolucion'],
            "fichas_normales": self.contadores_apertura['fichas_normales'],
            "fichas_promocion": self.contadores_apertura['fichas_promocion']
        }
        
        # Insertar cierre inicial con todo en 0 para registrar el día
        cierre_inicial = {
            "device_id": self.device_id,
            "fichas_expendidas": self.contadores_apertura['fichas_expendidas'],
            "dinero_ingresado": self.contadores_apertura['dinero_ingresado'],
            "promo1_contador": self.contadores_apertura['promo1_contador'],
            "promo2_contador": self.contadores_apertura['promo2_contador'],
            "promo3_contador": self.contadores_apertura['promo3_contador'],
            "fichas_devolucion": self.contadores_apertura['fichas_devolucion'],
            "fichas_normales": self.contadores_apertura['fichas_normales'],
            "fichas_promocion": self.contadores_apertura['fichas_promocion']
        }
        
        # Enviar cierre inicial al servidor remoto
        try:
            response = requests.post(DNS + urlCierres, json=cierre_inicial)
            if response.status_code == 200:
                print("Cierre inicial (apertura) enviado con éxito al servidor remoto")
            else:
                print(f"Error al enviar cierre inicial al servidor remoto: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error al conectar con el servidor remoto: {e}")
        
        # Enviar cierre inicial al servidor local
        try:
            response = requests.post(DNSLocal + urlCierres, json=cierre_inicial)
            if response.status_code == 200:
                print("Cierre inicial (apertura) enviado con éxito al servidor local")
            else:
                print(f"Error al enviar cierre inicial al servidor local: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error al conectar con el servidor local: {e}")
        
        self.actualizar_contadores_gui()
        self.guardar_configuracion()
        messagebox.showinfo("Apertura", "Apertura del día realizada con éxito.\nRegistro inicial creado en el sistema.")

    def realizar_cierre(self):
        # Realiza el cierre del día
        cierre_info = {
            "device_id": self.device_id,
            "fichas_expendidas": self.contadores_apertura['fichas_expendidas'],
            "dinero_ingresado": self.contadores_apertura['dinero_ingresado'],
            "promo1_contador": self.contadores_apertura['promo1_contador'],
            "promo2_contador": self.contadores_apertura['promo2_contador'],
            "promo3_contador": self.contadores_apertura['promo3_contador'],
            "fichas_devolucion": self.contadores_apertura['fichas_devolucion'],
            "fichas_normales": self.contadores_apertura['fichas_normales'],
            "fichas_promocion": self.contadores_apertura['fichas_promocion']
        }
        mensaje_cierre = (
            f"Fichas expendidas: {cierre_info['fichas_expendidas']}\n"
            f"Dinero ingresado: ${cierre_info['dinero_ingresado']:.2f}\n"
            f"Promo 1 usadas: {cierre_info['promo1_contador']}\n"
            f"Promo 2 usadas: {cierre_info['promo2_contador']}\n"
            f"Promo 3 usadas: {cierre_info['promo3_contador']}\n"
            f"--- Desglose ---\n"
            f"Vendidas: {cierre_info['fichas_normales']} | Promoción: {cierre_info['fichas_promocion']} | Devolución: {cierre_info['fichas_devolucion']}"
        )
        messagebox.showinfo("Cierre", f"Cierre del día realizado:\n{mensaje_cierre}")
        
        # Enviar datos al servidor
        try:
            response = requests.post(DNS + urlCierres, json=cierre_info)
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    if "error" in resp_json:
                        print(f"Error del servidor (Remoto): {resp_json['error']}")
                    else:
                        print("Datos de cierre enviados con éxito")
                except:
                    print("Datos de cierre enviados (Respuesta no JSON)")
            else:
                print(f"Error al enviar datos de cierre: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error al conectar con el servidor: {e}")

        try:
            response = requests.post(DNSLocal + urlCierres, json=cierre_info)
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    if "error" in resp_json:
                        print(f"Error del servidor (Local): {resp_json['error']}")
                    else:
                        print("Datos de cierre enviados con éxito")
                except:
                    print("Datos de cierre enviados (Respuesta no JSON)")
            else:
                print(f"Error al enviar datos de cierre: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error al conectar con el servidor: {e}")    
        
        # IMPORTANTE: Guardar los contadores parciales ANTES de resetear
        # para que el subcierre tenga los datos correctos
        self.contadores_parciales_pre_cierre = self.contadores_parciales.copy()
        
        self.contadores = {
            "fichas_expendidas": 0, 
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,   
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }

        self.contadores_apertura = {
            "fichas_expendidas": 0,
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }
        self.contadores_parciales = {
            "fichas_expendidas": 0,
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }
        
        # Marcar que se realizó un cierre para evitar doble reporte en cerrar_sesion
        self.cierre_realizado = True
        
        self.guardar_configuracion()

    def realizar_cierre_parcial(self):
        # Realiza el cierre parcial
        subcierre_info = {
            "device_id": self.device_id,
            "partial_fichas": self.contadores_parciales['fichas_expendidas'],
            "partial_dinero": self.contadores_parciales['dinero_ingresado'],
            "partial_p1": self.contadores_parciales['promo1_contador'],
            "partial_p2": self.contadores_parciales['promo2_contador'],
            "partial_p3": self.contadores_parciales['promo3_contador'],
            "partial_devolucion": self.contadores_parciales['fichas_devolucion'],
            "partial_normales": self.contadores_parciales['fichas_normales'],
            "partial_promocion": self.contadores_parciales['fichas_promocion'],
            "employee_id": self.username
        }

        mensaje_subcierre = (
            f"Fichas expendidas: {subcierre_info['partial_fichas']}\n"
            f"Dinero ingresado: ${subcierre_info['partial_dinero']:.2f}\n"
            f"Promo 1 usadas: {subcierre_info['partial_p1']}\n"
            f"Promo 2 usadas: {subcierre_info['partial_p2']}\n"
            f"Promo 3 usadas: {subcierre_info['partial_p3']}\n"
            f"Devoluciones: {subcierre_info['partial_devolucion']}"
        )
        messagebox.showinfo("Cierre Parcial", f"Cierre parcial realizado:\n{mensaje_subcierre}")

        # Enviar datos al servidor
        try:
            response = requests.post(DNS + urlSubcierre, json=subcierre_info)
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    if "error" in resp_json:
                        print(f"Error del servidor (Remoto): {resp_json['error']}")
                    else:
                        print("Datos de cierre parcial enviados con éxito")
                except:
                    print("Datos de cierre parcial enviados (Respuesta no JSON)")
            else:
                print(f"Error al enviar datos de cierre parcial: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error al conectar con el servidor: {e}")

        try:
            response = requests.post(DNSLocal + urlSubcierre, json=subcierre_info)
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    if "error" in resp_json:
                        print(f"Error del servidor (Local): {resp_json['error']}")
                    else:
                        print("Datos de cierre parcial enviados con éxito")
                except:
                    print("Datos de cierre parcial enviados (Respuesta no JSON)")
            else:
                print(f"Error al enviar datos de cierre parcial: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error al conectar con el servidor: {e}")

        # Reiniciar los contadores parciales
        self.contadores_parciales = {
            "fichas_expendidas": 0,
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }
        self.guardar_configuracion()

    def cerrar_sesion(self):
        # Determinar qué contadores usar para el subcierre
        # Si se hizo un cierre del día, usar los contadores guardados antes del cierre
        # Si NO se hizo cierre, usar los contadores parciales actuales
        if hasattr(self, 'cierre_realizado') and self.cierre_realizado:
            # Ya se hizo un cierre del día, usar los contadores guardados
            contadores_a_enviar = getattr(self, 'contadores_parciales_pre_cierre', {
                "fichas_expendidas": 0,
                "dinero_ingresado": 0,
                "promo1_contador": 0,
                "promo2_contador": 0,
                "promo3_contador": 0,
                "fichas_devolucion": 0,
                "fichas_normales": 0,
                "fichas_promocion": 0
            })
            print("[GUI] Usando contadores pre-cierre para subcierre")
        else:
            # No se hizo cierre, usar contadores parciales actuales
            contadores_a_enviar = self.contadores_parciales
            print("[GUI] Usando contadores parciales actuales para subcierre")
        
        # Solo enviar subcierre si hay datos relevantes
        tiene_datos = (
            contadores_a_enviar['fichas_expendidas'] > 0 or
            contadores_a_enviar['dinero_ingresado'] > 0 or
            contadores_a_enviar['promo1_contador'] > 0 or
            contadores_a_enviar['promo2_contador'] > 0 or
            contadores_a_enviar['promo3_contador'] > 0 or
            contadores_a_enviar['fichas_devolucion'] > 0
        )
        
        if tiene_datos:
            Subcierre_info = {
                "device_id": self.device_id,
                "partial_fichas": contadores_a_enviar['fichas_expendidas'],
                "partial_dinero": contadores_a_enviar['dinero_ingresado'],
                "partial_p1": contadores_a_enviar['promo1_contador'],
                "partial_p2": contadores_a_enviar['promo2_contador'],
                "partial_p3": contadores_a_enviar['promo3_contador'],
                "partial_devolucion": contadores_a_enviar['fichas_devolucion'],
                "partial_normales": contadores_a_enviar['fichas_normales'],
                "partial_promocion": contadores_a_enviar['fichas_promocion'],
                "employee_id": self.username
            }

            # Enviar datos al servidor
            try:
                response = requests.post(DNS + urlSubcierre, json=Subcierre_info)
                if response.status_code == 200:
                    try:
                        resp_json = response.json()
                        if "error" in resp_json:
                            print(f"Error del servidor (Remoto): {resp_json['error']}")
                        else:
                            print("Datos de cierre parcial enviados con éxito")
                    except:
                        print("Datos de cierre parcial enviados (Respuesta no JSON)")
                else:
                    print(f"Error al enviar datos de cierre parcial: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Error al conectar con el servidor: {e}")

            try:
                response = requests.post(DNSLocal + urlSubcierre, json=Subcierre_info)
                if response.status_code == 200:
                    try:
                        resp_json = response.json()
                        if "error" in resp_json:
                            print(f"Error del servidor (Local): {resp_json['error']}")
                        else:
                            print("Datos de cierre parcial enviados con éxito")
                    except:
                        print("Datos de cierre parcial enviados (Respuesta no JSON)")
                else:
                    print(f"Error al enviar datos de cierre parcial: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Error al conectar con el servidor: {e}")
        else:
            print("[GUI] No hay datos para enviar en el subcierre")

        # Reiniciar los contadores para la próxima sesión
        self.contadores = {
            "fichas_expendidas": 0,
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }
        self.contadores_parciales = {
            "fichas_expendidas": 0,
            "dinero_ingresado": 0,
            "promo1_contador": 0,
            "promo2_contador": 0,
            "promo3_contador": 0,
            "fichas_restantes": 0,
            "fichas_devolucion": 0,
            "fichas_normales": 0,
            "fichas_promocion": 0
        }
        
        # Actualizar la GUI con los contadores en cero ANTES de guardar
        self.actualizar_contadores_gui()
        self.guardar_configuracion()

        messagebox.showinfo("Cerrar Sesión", "La sesión ha sido cerrada.")
        self.root.destroy()

        # Crear nueva instancia de UserManagement y pasar el callback
        def iniciar_expendedora(username):
            nuevo_root = tk.Tk()
            app = ExpendedoraGUI(nuevo_root, username)
            nuevo_root.mainloop()

        user_management = UserManagement(iniciar_expendedora)
        user_management.run()
        
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
        
        # Forzar a Tkinter a procesar las actualizaciones de los widgets inmediatamente
        self.root.update_idletasks()

    def expender_fichas_gui(self):
        """Ya no es necesaria - el hardware controla todo automáticamente"""
        pass

    def simular_billetero(self):
        messagebox.showinfo("Simulación", "Billetero activado: Se ha ingresado dinero.")

    def simular_barrera(self):
        messagebox.showinfo("Simulación", "Barrera activada: Se detectó una ficha.")

    def simular_entrega_fichas(self):
        from gpio_sim import GPIO
        # Simular flanco descendente en el sensor ENTHOPER
        GPIO.simulate_sensor_pulse(core.ENTHOPER)
        
    def simular_salida_fichas(self):
        """Simula el sensor del hopper detectando una ficha (para pruebas)"""
        from gpio_sim import GPIO

        # Simular flanco descendente en el sensor ENTHOPER
        GPIO.simulate_sensor_pulse(core.ENTHOPER)
        # messagebox.showinfo("Simulación", "Sensor del hopper activado - Ficha expendida")
            
    def simular_promo(self, promo):
        # Enviar comando al core via buffer compartido
        fichas = self.promociones[promo]["fichas"]
        promo_num = int(promo.split()[1])
        shared_buffer.gui_to_core_queue.put({'type': 'promo', 'promo_num': promo_num, 'fichas': fichas})
        # print(f"[GUI] Comando promo enviado: {promo}, fichas: {fichas}")

        # Aumentar el dinero ingresado según el precio de la promoción
        precio = self.promociones[promo]["precio"]
        self.contadores["dinero_ingresado"] += precio
        self.contadores_apertura["dinero_ingresado"] += precio
        self.contadores_parciales["dinero_ingresado"] += precio

        # Registrar fichas de promoción
        self.contadores["fichas_promocion"] += fichas
        self.contadores_apertura["fichas_promocion"] += fichas
        self.contadores_parciales["fichas_promocion"] += fichas

        self.contadores_labels["dinero_ingresado"].config(text=f"Dinero ingresado: ${self.contadores['dinero_ingresado']:.2f}")

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
            self.contadores_labels[promo_contadores[promo]].config(text=f"{promo} usadas: {self.contadores[promo_contadores[promo]]}")
        else:
            messagebox.showerror("Error", "Promoción no válida.")

        self.actualizar_contadores_gui()
        self.guardar_configuracion()

    def actualizar_fecha_hora(self):
        # Obtener la fecha y hora actual
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S")
        self.footer_label.config(text=current_time)  # Actualizar el label del footer
        self._after_id = self.root.after(1000, self.actualizar_fecha_hora)  # Llamar a esta función cada segundo

    # NOTA: Esta función ya no es necesaria - ahora usamos callbacks en tiempo real
    # def actualizar_desde_hardware(self):
    #     Los callbacks on_ficha_expendida() y on_fichas_agregadas()
    #     actualizan la GUI inmediatamente cuando hay cambios en el hardware

if __name__ == "__main__":
    root = tk.Tk()
    app = ExpendedoraGUI(root, "username")  # Reemplazar "username" con el nombre de usuario actual

    root.mainloop()
