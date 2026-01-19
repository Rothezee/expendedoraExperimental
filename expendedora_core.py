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

#GPIO.setwarnings(False) descomentar para usar en hardware real

# --- CONFIGURACIÓN DE PINES ---
MOTOR_PIN = 24  # Pin del motor
ENTHOPER = 16  # Sensor para contar fichas que salen

# --- CONFIGURACIÓN DEL SENSOR ---
PULSO_MIN = 0.05  # Duración mínima del pulso (50ms) - filtro de ruido
PULSO_MAX = 0.5   # Duración máxima del pulso (500ms) - filtro de bloqueos

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
DB_FILE = "expendedora.db"

# --- CONFIGURACIÓN DE SERVIDORES ---
SERVER_HEARTBEAT = "https://maquinasbonus.com/esp32_project/insert_heartbeat.php"

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
        return {"promociones": {}, "valor_ficha": 1.0, "device_id": ""}

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
    """
    NOTA: Esta función se llama cuando el motor se detiene.
        Aquí se deben obtener los datos relevantes de la venta que acaba de terminar.
        Enviamos el contador TOTAL para el servidor, no el de sesión.
    """

    DNS = "https://maquinasbonus.com/"  # DNS servidor
    DNSLocal = "http://127.0.0.1/"  # DNS servidor local
    url = "esp32_project/expendedora/insert_data_expendedora.php"  # URL de datos generales

    config = cargar_configuracion()
    device_id = config.get("device_id")

    datos = {
        "device_id": device_id,
        "dato1": int(shared_buffer.get_fichas_expendidas_total()), # Usar contador TOTAL
        "dato2": int(shared_buffer.get_r_cuenta()) # Asegurar que es entero
    }
    try:
        # Usamos la URL de datos generales para reportar la venta
        response = requests.post(DNSLocal + url, json=datos)
        # print(f"[REPORTE VENTA] Datos de venta enviados. Respuesta: {response.status_code}")
    except requests.RequestException as e:
        print(f"[ERROR REPORTE VENTA] No se pudo enviar el reporte de venta: {e}")

    try:
        # Usamos la URL de datos generales para reportar la venta
        response = requests.post(DNS + url, json=datos)
    except requests.RequestException as e:
        print(f"[ERROR REPORTE VENTA] No se pudo enviar el reporte de venta: {e}")

# --- ENVÍO DE DATOS AL SERVIDOR ---
def enviar_pulso():
    config = cargar_configuracion()
    device_id = config.get("device_id")
    data = {"device_id": device_id}
    try:
        response = requests.post(SERVER_HEARTBEAT, json=data)
        # print("Heartbeat enviado:", response.text)
    except requests.RequestException as e:
        print("Error enviando heartbeat:", e)

    threading.Timer(60, enviar_pulso).start()  

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

# --- CONVERSIÓN DE DINERO A FICHAS ---
def convertir_fichas():
    valor1 = get_config("VALOR1", 1000)
    valor2 = get_config("VALOR2", 5000)
    valor3 = get_config("VALOR3", 10000)
    fichas1 = get_config("FICHAS1", 1)
    fichas2 = get_config("FICHAS2", 2)
    fichas3 = get_config("FICHAS3", 5)
    
    cuenta = shared_buffer.get_cuenta()
    fichas_a_agregar = 0
    # Lógica para determinar cuántas fichas agregar basado en 'cuenta'
    if cuenta >= valor1:
        fichas_a_agregar = fichas1
        shared_buffer.add_to_cuenta(-valor1)
    
    if fichas_a_agregar > 0:
        shared_buffer.agregar_fichas(fichas_a_agregar)

# --- FUNCIONES PARA LA GUI ---
def obtener_dinero_ingresado():
    return shared_buffer.get_cuenta()

def obtener_fichas_disponibles():
    # return get_fichas_restantes() linea que funcionaba anteriormente 12/3/2025
    return shared_buffer.get_fichas_restantes()
def expender_fichas(cantidad):
    """
    Función llamada desde la GUI para agregar fichas al dispensador
    """
    shared_buffer.agregar_fichas(cantidad)

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
