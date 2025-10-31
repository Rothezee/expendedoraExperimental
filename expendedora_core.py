from gpio_sim import GPIO  # import RPi.GPIO as GPIO  # Descomentar para usar en hardware real
import time
import requests
import sqlite3
import threading
import json
import os
from datetime import datetime
import shared_buffer

config_file = "config.json"
registro_file = "registro.json"

# --- CONFIGURACIÓN DE PINES ---
MOTOR_PIN = 24  # Pin del motor
ENTHOPER = 23  # Sensor para contar fichas que salen

# --- CONFIGURACIÓN DEL SENSOR ---
PULSO_MIN = 0.05  # Duración mínima del pulso (50ms) - filtro de ruido
PULSO_MAX = 0.5   # Duración máxima del pulso (500ms) - filtro de bloqueos

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
DB_FILE = "expendedora.db"

# --- CONFIGURACIÓN DE SERVIDORES ---
SERVER_HEARTBEAT = "http://127.0.0.1/esp32_project/insert_heartbeat.php"
SERVER_CIERRE = "http://127.0.0.1/esp32_project/insert_close_expendedora.php"

# --- VARIABLES DEL SISTEMA ---
# Variables globales removidas, ahora se usan shared_buffer

# --- LOCK PARA THREADING ---
fichas_lock = threading.Lock()

# --- CALLBACK SIMPLE PARA NOTIFICAR CAMBIOS ---
gui_actualizar_funcion = None  # Función simple que actualiza la GUI cuando cambian los contadores

def registrar_gui_actualizar(funcion):
    """Registra la función de actualización de la GUI"""
    global gui_actualizar_funcion
    gui_actualizar_funcion = funcion
    # print("[CORE] Función de actualización GUI registrada")

def get_fichas_restantes():
    """Obtener fichas_restantes de forma thread-safe"""
    return shared_buffer.get_fichas_restantes()

def get_fichas_expendidas():
    """Obtener fichas_expendidas de forma thread-safe"""
    return shared_buffer.get_fichas_expendidas()

# ----------CONEXION CON GUI Y LOGICA PARA GUARDAR REGISTROS---------------
def cargar_configuracion():
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    else:
        return {"promociones": {}, "valor_ficha": 1.0}

def guardar_configuracion(config):
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)

def iniciar_apertura():
    registro = {
        "apertura": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "fichas_expendidas": 0,
        "dinero_ingresado": 0,
        "promociones_usadas": {
            "Promo 1": 0,
            "Promo 2": 0,
            "Promo 3": 0
        }
    }
    guardar_registro(registro)
    return registro

def cargar_registro():
    if os.path.exists(registro_file):
        with open(registro_file, 'r') as f:
            return json.load(f)
    else:
        return iniciar_apertura()

def guardar_registro(registro):
    with open(registro_file, 'w') as f:
        json.dump(registro, f, indent=4)

def actualizar_registro(tipo, cantidad):
    registro = cargar_registro()
    if tipo == "ficha":
        registro["fichas_expendidas"] += cantidad
        registro["dinero_ingresado"] += cantidad * cargar_configuracion()["valor_ficha"]
    elif tipo in ["Promo 1", "Promo 2", "Promo 3"]:
        registro["promociones_usadas"][tipo] += 1
        registro["dinero_ingresado"] += cargar_configuracion()["promociones"][tipo]["precio"]
    guardar_registro(registro)

def realizar_cierre():
    registro = cargar_registro()
    registro["cierre"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    guardar_registro(registro)
    return registro

# --- FUNCIONES PARA REGISTRAR CALLBACKS ---

# --- CONFIGURACIÓN GPIO ---
GPIO.setmode(GPIO.BCM)

# Configurar sensor como entrada
GPIO.setup(ENTHOPER, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Configurar motor como salida
GPIO.setup(MOTOR_PIN, GPIO.OUT)
GPIO.output(MOTOR_PIN, GPIO.LOW)

# --- CONFIGURACIÓN DE BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor INTEGER)''')
    conn.commit()
    conn.close()

def get_config(clave, default=0):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE clave=?", (clave,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_config(clave, valor):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO config (clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor=?", (clave, valor, valor))
    conn.commit()
    conn.close()

def enviar_datos_venta_servidor():
    """Envía los datos de la última venta al servidor."""
    # NOTA: Esta función se llama cuando el motor se detiene.
    # Aquí se deben obtener los datos relevantes de la venta que acaba de terminar.
    # Por ahora, enviamos los contadores totales como ejemplo.
    # En el futuro, se podría implementar un sistema para rastrear ventas individuales.
    datos = {
        "device_id": "EXPENDEDORA_1",
        "dato1": int(shared_buffer.get_fichas_expendidas()), # Asegurar que es entero
        "dato2": int(shared_buffer.get_r_cuenta()) # Asegurar que es float
    }
    try:
        # Usamos la URL de datos generales para reportar la venta
        response = requests.post("http://127.0.0.1/esp32_project/expendedora/insert_data_expendedora.php", json=datos)
        # print(f"[REPORTE VENTA] Datos de venta enviados. Respuesta: {response.status_code}")
    except requests.RequestException as e:
        print(f"[ERROR REPORTE VENTA] No se pudo enviar el reporte de venta: {e}")

# --- ENVÍO DE DATOS AL SERVIDOR ---
def enviar_pulso():
    data = {"device_id": "EXPENDEDORA_1"}
    try:
        response = requests.post(SERVER_HEARTBEAT, json=data)
        # print("Heartbeat enviado:", response.text)
    except requests.RequestException as e:
        print("Error enviando heartbeat:", e)

    threading.Timer(60, enviar_pulso).start()  

def enviar_cierre_diario():
    data = {
        "device_id": "EXPENDEDORA_1",
        "dato1": shared_buffer.get_promo_count(3),
        "dato2": shared_buffer.get_r_cuenta(),
        "dato3": shared_buffer.get_promo_count(1),
        "dato4": shared_buffer.get_promo_count(2),
        "dato5": shared_buffer.get_r_sal()
    }

    try:
        response = requests.post(SERVER_CIERRE, json=data)
        # print("Cierre enviado:", response.text)
    except requests.RequestException as e:
        print("Error enviando cierre:", e)

    shared_buffer.set_r_cuenta(0)
    shared_buffer.set_r_sal(0)
    shared_buffer.set_promo_count(1, 0)
    shared_buffer.set_promo_count(2, 0)
    shared_buffer.set_promo_count(3, 0)

# --- CONTROL DEL MOTOR Y CONTEO DE FICHAS ---
import time

def controlar_motor():
    """
    Hilo que controla el motor basándose en fichas_restantes.
    - Motor activo si fichas_restantes > 0
    - Motor apagado si fichas_restantes == 0
    - Sensor cuenta fichas que salen y decrementa fichas_restantes
    - Implementa detección de pulso completo (HIGH->LOW->HIGH)
    - La GUI lee directamente las variables globales (thread-safe via funciones get)
    """
    estado_anterior_sensor = GPIO.input(ENTHOPER)
    ficha_en_sensor = False  # Flag para detectar pulso completo
    tiempo_inicio_pulso = 0

    # print("[CORE] Iniciando hilo de control de motor")

    while True:
        # Procesar comandos desde la GUI
        shared_buffer.process_gui_commands()

        # Control del motor basado en fichas_restantes
        if shared_buffer.get_fichas_restantes() > 0:
            if not shared_buffer.get_motor_activo():
                GPIO.output(MOTOR_PIN, GPIO.HIGH)
                shared_buffer.set_motor_activo(True)
                # print(f"[MOTOR ON] Fichas pendientes: {shared_buffer.get_fichas_restantes()}")
        else:
            if shared_buffer.get_motor_activo():
                GPIO.output(MOTOR_PIN, GPIO.LOW)
                shared_buffer.set_motor_activo(False)
                # print("[MOTOR OFF] Todas las fichas expendidas")
                # Enviar reporte de la venta que acaba de terminar
                enviar_datos_venta_servidor()

        # Leer estado actual del sensor
        estado_actual_sensor = GPIO.input(ENTHOPER)
        tiempo_actual = time.time()

        # Máquina de estados para detección de pulso completo
        if not ficha_en_sensor:
            # Estado: Esperando ficha (sensor en HIGH)
            if estado_anterior_sensor == GPIO.HIGH and estado_actual_sensor == GPIO.LOW:
                # Flanco descendente detectado - Ficha entrando
                ficha_en_sensor = True
                tiempo_inicio_pulso = tiempo_actual
                # print(f"[SENSOR] Ficha detectada entrando...")
        else:
            # Estado: Ficha en el sensor (esperando que salga)
            if estado_actual_sensor == GPIO.HIGH:
                # Flanco ascendente - Ficha salió completamente
                duracion_pulso = tiempo_actual - tiempo_inicio_pulso

                # Verificar que el pulso duró un tiempo razonable
                if PULSO_MIN <= duracion_pulso <= PULSO_MAX:
                    cambio_realizado = False
                    if shared_buffer.get_fichas_restantes() > 0:
                        shared_buffer.decrementar_fichas_restantes()
                        cambio_realizado = True
                        # print(f"[FICHA EXPENDIDA] Restantes: {shared_buffer.get_fichas_restantes()} | Total: {shared_buffer.get_fichas_expendidas()} | Duración: {duracion_pulso*1000:.1f}ms")

                        # Actualizar registro
                        actualizar_registro("ficha", 1)
                    else:
                        print("[ADVERTENCIA] Sensor detectó ficha pero contador ya está en 0")

                    # NOTIFICAR A LA GUI (fuera del lock para evitar deadlock)
                    if cambio_realizado and gui_actualizar_funcion:
                        try:
                            gui_actualizar_funcion()
                        except Exception as e:
                            print(f"[ERROR] GUI actualizar falló: {e}")

                elif duracion_pulso < PULSO_MIN:
                    print(f"[RUIDO IGNORADO] Pulso muy corto: {duracion_pulso*1000:.1f}ms")
                else:
                    print(f"[ADVERTENCIA] Pulso muy largo: {duracion_pulso*1000:.1f}ms")

                ficha_en_sensor = False

        estado_anterior_sensor = estado_actual_sensor
        time.sleep(0.005)  # 5ms de polling - más rápido para mejor detección
# --- FUNCIÓN PARA AGREGAR FICHAS (LLAMADA DESDE LA GUI) ---
def agregar_fichas(cantidad):
    """
    Agrega fichas al contador para que el motor las expenda.
    Notifica a la GUI inmediatamente del cambio.
    """
    global fichas_restantes

    with fichas_lock:
        fichas_restantes += cantidad
        # print(f"[FICHAS AGREGADAS] +{cantidad} | Total pendientes: {fichas_restantes}")

    # NOTIFICAR A LA GUI (fuera del lock)
    if gui_actualizar_funcion:
        try:
            gui_actualizar_funcion()
        except Exception as e:
            print(f"[ERROR] GUI actualizar falló: {e}")

    return fichas_restantes

def obtener_fichas_restantes():
    """
    Retorna la cantidad de fichas pendientes por expender
    """
    with fichas_lock:
        return fichas_restantes

def obtener_fichas_expendidas():
    """
    Retorna la cantidad de fichas ya expendidas
    """
    return shared_buffer.get_fichas_expendidas()

# --- CONVERSIÓN DE DINERO A FICHAS ---
def convertir_fichas():
    global cuenta, fichas_restantes, r_sal

    valor1 = get_config("VALOR1", 1000)
    valor2 = get_config("VALOR2", 5000)
    valor3 = get_config("VALOR3", 10000)
    fichas1 = get_config("FICHAS1", 1)
    fichas2 = get_config("FICHAS2", 2)
    fichas3 = get_config("FICHAS3", 5)

    with fichas_lock:
        if cuenta >= valor1 and cuenta < valor2:
            fichas_restantes += fichas1
            cuenta -= valor1
        elif cuenta >= valor2 and cuenta < valor3:
            fichas_restantes += fichas2
            cuenta -= valor2
        elif cuenta >= valor3:
            fichas_restantes += fichas3
            cuenta -= valor3

        r_sal += fichas_restantes

# --- FUNCIONES PARA LA GUI ---
def obtener_dinero_ingresado():
    return cuenta

def obtener_fichas_disponibles():
    return obtener_fichas_restantes()

def expender_fichas(cantidad):
    """
    Función llamada desde la GUI para agregar fichas al dispensador
    """
    return agregar_fichas(cantidad)

# --- PROGRAMA PRINCIPAL ---
def iniciar_sistema():
    """Inicializa el sistema de control de motor (sin GUI)"""
    init_db()
    enviar_pulso()

    # Iniciar hilo de control del motor
    motor_thread = threading.Thread(target=controlar_motor, daemon=True)
    motor_thread.start()
    # print("Sistema de control de motor iniciado")

    return motor_thread

def detener_sistema():
    """Apaga el motor y limpia GPIO"""
    GPIO.output(MOTOR_PIN, GPIO.LOW)
    GPIO.cleanup()
    # print("Sistema detenido")
