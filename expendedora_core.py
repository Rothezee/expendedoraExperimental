from gpio_sim import GPIO  # import RPi.GPIO as GPIO  # Descomentar para usar en hardware real
import time
import requests
import sqlite3
import threading
import json
import os
from datetime import datetime

config_file = "config.json"
registro_file = "registro.json"

# --- CONFIGURACIÓN DE PINES ---
MOTOR_PIN = 24  # Pin del motor
ENTHOPER = 23  # Sensor para contar fichas que salen

# --- CONFIGURACIÓN DEL SENSOR ---
DEBOUNCE_TIME = 0.3  # Tiempo mínimo entre fichas (segundos) - ajustar según velocidad del motor

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
DB_FILE = "expendedora.db"

# --- CONFIGURACIÓN DE SERVIDORES ---
SERVER_HEARTBEAT = "http://192.168.1.33/esp32_project/insert_heartbeat.php"
SERVER_CIERRE = "http://192.168.1.33/esp32_project/insert_close_expendedora.php"

# --- VARIABLES DEL SISTEMA ---
cuenta = 0
fichas_restantes = 0  # Contador de fichas pendientes por expender
fichas_expendidas = 0  # Contador de fichas ya expendidas
r_cuenta = 0
r_sal = 0
promo1_count = 0
promo2_count = 0
promo3_count = 0
motor_activo = False

# --- LOCK PARA THREADING ---
fichas_lock = threading.Lock()

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

# --- ENVÍO DE DATOS AL SERVIDOR ---
def enviar_pulso():
    data = {"device_id": "EXPENDEDORA_1"}
    try:
        response = requests.post(SERVER_HEARTBEAT, json=data)
        print("Heartbeat enviado:", response.text)
    except requests.RequestException as e:
        print("Error enviando heartbeat:", e)

    threading.Timer(60, enviar_pulso).start()  

def enviar_cierre_diario():
    global r_cuenta, r_sal, promo1_count, promo2_count, promo3_count

    data = {
        "device_id": "EXPENDEDORA_1",
        "dato1": promo3_count,
        "dato2": r_cuenta,
        "dato3": promo1_count,
        "dato4": promo2_count,
        "dato5": r_sal
    }
    
    try:
        response = requests.post(SERVER_CIERRE, json=data)
        print("Cierre enviado:", response.text)
    except requests.RequestException as e:
        print("Error enviando cierre:", e)

    r_cuenta = r_sal = promo1_count = promo2_count = promo3_count = 0  

# --- CONTROL DEL MOTOR Y CONTEO DE FICHAS ---
def controlar_motor():
    """
    Hilo que controla el motor basado en fichas_restantes.
    - Motor activo si fichas_restantes > 0
    - Motor apagado si fichas_restantes == 0
    - Sensor cuenta fichas que salen y decrementa fichas_restantes
    - Implementa anti-rebote con DEBOUNCE_TIME
    """
    global motor_activo, fichas_restantes, fichas_expendidas

    estado_anterior_sensor = GPIO.input(ENTHOPER)
    ultimo_conteo = 0  # Para anti-rebote

    while True:
        # Control del motor
        if fichas_restantes > 0 and not motor_activo:
            GPIO.output(MOTOR_PIN, GPIO.HIGH)
            motor_activo = True
            print(f"[MOTOR ON] Fichas pendientes: {fichas_restantes}")
        elif fichas_restantes <= 0 and motor_activo:
            GPIO.output(MOTOR_PIN, GPIO.LOW)
            motor_activo = False
            print("[MOTOR OFF] Todas las fichas expendidas")

        # Detección de fichas que salen (flanco descendente)
        estado_actual_sensor = GPIO.input(ENTHOPER)
        tiempo_actual = time.time()
        if estado_anterior_sensor == GPIO.HIGH and estado_actual_sensor == GPIO.LOW:
            # Anti-rebote: esperar DEBOUNCE_TIME entre pulsos válidos
            if tiempo_actual - ultimo_conteo >= DEBOUNCE_TIME:
                if fichas_restantes > 0:
                    fichas_restantes -= 1
                    fichas_expendidas += 1
                    ultimo_conteo = tiempo_actual
                    print(f"[FICHA EXPENDIDA] Restantes: {fichas_restantes}")
            else:
                print(f"[REBOTE IGNORADO] Delay: {tiempo_actual - ultimo_conteo:.2f}s")
        estado_anterior_sensor = estado_actual_sensor

        # Pequeña pausa para evitar ocupar CPU
        time.sleep(0.01)

# --- FUNCIÓN PARA AGREGAR FICHAS (LLAMADA DESDE LA GUI) ---
def agregar_fichas(cantidad):
    """
    Agrega fichas al contador para que el motor las expenda
    """
    global fichas_restantes
    
    with fichas_lock:
        fichas_restantes += cantidad
        print(f"Fichas agregadas: {cantidad} | Total pendientes: {fichas_restantes}")
    
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
    with fichas_lock:
        return fichas_expendidas

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
    print("Sistema de control de motor iniciado")

    return motor_thread

def detener_sistema():
    """Apaga el motor y limpia GPIO"""
    GPIO.output(MOTOR_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("Sistema detenido")
