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
PULSO_MIN = 0.05  # Duración mínima del pulso (50ms) - filtro de ruido
PULSO_MAX = 0.5   # Duración máxima del pulso (500ms) - filtro de bloqueos

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

# --- CALLBACK PARA NOTIFICAR CAMBIOS A LA GUI ---
callback_ficha_expendida = None  # Función que se llama cuando sale una ficha
callback_fichas_agregadas = None  # Función que se llama cuando se agregan fichas

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
def registrar_callback_ficha_expendida(funcion):
    """Registra una función que se llamará cada vez que salga una ficha"""
    global callback_ficha_expendida
    callback_ficha_expendida = funcion

def registrar_callback_fichas_agregadas(funcion):
    """Registra una función que se llamará cada vez que se agreguen fichas"""
    global callback_fichas_agregadas
    callback_fichas_agregadas = funcion

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
import time

def controlar_motor():
    """
    Hilo que controla el motor basándose en fichas_restantes.
    - Motor activo si fichas_restantes > 0
    - Motor apagado si fichas_restantes == 0
    - Sensor cuenta fichas que salen y decrementa fichas_restantes
    - Implementa detección de pulso completo (HIGH->LOW->HIGH)
    - Notifica a la GUI mediante callback cuando sale una ficha
    """
    global motor_activo, fichas_restantes, fichas_expendidas, callback_ficha_expendida

    estado_anterior_sensor = GPIO.input(ENTHOPER)
    ficha_en_sensor = False  # Flag para detectar pulso completo
    tiempo_inicio_pulso = 0

    print("[CORE] Iniciando hilo de control de motor")

    while True:
        # Control del motor basado en fichas_restantes
        with fichas_lock:
            if fichas_restantes > 0:
                # Hay fichas pendientes - Motor debe estar encendido
                if not motor_activo:
                    GPIO.output(MOTOR_PIN, GPIO.HIGH)
                    motor_activo = True
                    print(f"[MOTOR ON] Fichas pendientes: {fichas_restantes}")
            else:
                # No hay fichas pendientes - Motor debe estar apagado
                if motor_activo:
                    GPIO.output(MOTOR_PIN, GPIO.LOW)
                    motor_activo = False
                    print("[MOTOR OFF] Todas las fichas expendidas")

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
                print(f"[SENSOR] Ficha detectada entrando...")
        else:
            # Estado: Ficha en el sensor (esperando que salga)
            if estado_actual_sensor == GPIO.HIGH:
                # Flanco ascendente - Ficha salió completamente
                duracion_pulso = tiempo_actual - tiempo_inicio_pulso

                # Verificar que el pulso duró un tiempo razonable
                if PULSO_MIN <= duracion_pulso <= PULSO_MAX:
                    # Contar la ficha
                    with fichas_lock:
                        if fichas_restantes > 0:
                            fichas_restantes -= 1
                            fichas_expendidas += 1
                            print(f"[FICHA EXPENDIDA] Restantes: {fichas_restantes} | Total: {fichas_expendidas} | Duración: {duracion_pulso*1000:.1f}ms")

                            # Actualizar registro
                            actualizar_registro("ficha", 1)

                            # NOTIFICAR A LA GUI INMEDIATAMENTE
                            if callback_ficha_expendida:
                                try:
                                    callback_ficha_expendida(fichas_restantes, fichas_expendidas)
                                except Exception as e:
                                    print(f"[ERROR] Callback GUI falló: {e}")

                            # Si se acabaron las fichas, forzar actualización GUI
                            if fichas_restantes == 0:
                                print(f"[CORE→GUI] Todas las fichas expendidas. Total: {fichas_expendidas}")
                                if callback_ficha_expendida:
                                    try:
                                        # Llamar de nuevo para asegurar actualización final
                                        callback_ficha_expendida(0, fichas_expendidas)
                                    except Exception as e:
                                        print(f"[ERROR] Callback final falló: {e}")
                        else:
                            print("[ADVERTENCIA] Sensor detectó ficha pero contador ya está en 0")
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
    Agrega fichas al contador para que el motor las expenda
    Notifica a la GUI mediante callback
    """
    global fichas_restantes, callback_fichas_agregadas

    with fichas_lock:
        fichas_restantes += cantidad
        print(f"[FICHAS AGREGADAS] +{cantidad} | Total pendientes: {fichas_restantes}")

        # NOTIFICAR A LA GUI INMEDIATAMENTE
        if callback_fichas_agregadas:
            try:
                callback_fichas_agregadas(fichas_restantes)
            except Exception as e:
                print(f"[ERROR] Callback GUI falló: {e}")

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
