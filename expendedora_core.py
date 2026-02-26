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

# --- ESCRITURA A DISCO CON DEBOUNCE ---
# Evita escribir registro.json en cada ficha (costoso en SD card).
# Acumula cambios y escribe UNA sola vez después de 2 segundos de inactividad.
_registro_pendiente = {}
_registro_lock = threading.Lock()
_registro_timer = None

def _flush_registro():
    """Escribe el registro acumulado al disco (llamado por el timer)."""
    global _registro_pendiente, _registro_timer
    with _registro_lock:
        if _registro_pendiente:
            if os.path.exists(registro_file):
                with open(registro_file, 'r') as f:
                    registro = json.load(f)
            else:
                registro = iniciar_apertura.__wrapped__() if hasattr(iniciar_apertura, '__wrapped__') else {
                    "apertura": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "fichas_expendidas": 0, "dinero_ingresado": 0,
                    "promociones_usadas": {"Promo 1": 0, "Promo 2": 0, "Promo 3": 0}
                }
            registro["fichas_expendidas"] += _registro_pendiente.get("fichas", 0)
            registro["dinero_ingresado"] += _registro_pendiente.get("dinero", 0)
            for promo, qty in _registro_pendiente.get("promos", {}).items():
                registro["promociones_usadas"][promo] += qty
            with open(registro_file, 'w') as f:
                json.dump(registro, f, indent=4)
            print(f"[REGISTRO] Guardado: +{_registro_pendiente.get('fichas',0)} fichas, +{_registro_pendiente.get('dinero',0):.2f} dinero")
            _registro_pendiente = {}
        _registro_timer = None

def _programar_flush_registro():
    """Cancela el timer anterior y programa uno nuevo (debounce 2s)."""
    global _registro_timer
    with _registro_lock:
        if _registro_timer is not None:
            _registro_timer.cancel()
        _registro_timer = threading.Timer(2.0, _flush_registro)
        _registro_timer.daemon = True
        _registro_timer.start()

#GPIO.setwarnings(False) descomentar para usar en hardware real

# --- CONFIGURACIÓN DE PINES ---
MOTOR_PIN = 24  # Pin del motor
ENTHOPER = 16  # Sensor para contar fichas que salen

# --- CONFIGURACIÓN DEL SENSOR ---
PULSO_MIN = 0.05  # Duración mínima del pulso (50ms) - filtro de ruido
PULSO_MAX = 0.5   # Duración máxima del pulso (500ms) - filtro de bloqueos

# --- CONFIGURACIÓN DE PROTECCIÓN DEL MOTOR ---
TIMEOUT_MOTOR = 3.0  # 3 segundos máximo sin dispensar ficha (PROTECCIÓN ANTI-QUEMADO)

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
DB_FILE = "expendedora.db"

# --- CONFIGURACIÓN DE SERVIDORES ---
SERVER_HEARTBEAT = "https://maquinasbonus.com/esp32_project/insert_heartbeat.php"

# --- CALLBACK SIMPLE PARA NOTIFICAR CAMBIOS ---
gui_actualizar_funcion = None  # Función simple que actualiza la GUI cuando cambian los contadores
gui_alerta_motor_funcion = None  # Función para alertar sobre motor trabado

# Variable global para controlar el bloqueo por emergencia
bloqueo_emergencia = False

def registrar_gui_actualizar(funcion):
    """Registra la función de actualización de la GUI"""
    global gui_actualizar_funcion
    gui_actualizar_funcion = funcion
    # print("[CORE] Función de actualización GUI registrada")

def registrar_gui_alerta_motor(funcion):
    """Registra la función de alerta de motor trabado para la GUI"""
    global gui_alerta_motor_funcion
    gui_alerta_motor_funcion = funcion
    # print("[CORE] Función de alerta motor GUI registrada")

def desbloquear_motor():
    """Permite reanudar el motor después de un bloqueo por timeout"""
    global bloqueo_emergencia
    bloqueo_emergencia = False
    print("[CORE] Motor desbloqueado por usuario, reanudando operación...")

def vaciar_fichas_restantes():
    """Resetea el contador de fichas restantes a 0"""
    shared_buffer.set_fichas_restantes(0)
    print("[CORE] Contador de fichas vaciado (0) por solicitud de usuario.")
    
    # Notificar a la GUI para que se sincronice
    if gui_actualizar_funcion:
        try:
            gui_actualizar_funcion()
        except Exception as e:
            print(f"[ERROR] GUI actualizar falló: {e}")

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
    """Acumula cambios en memoria y escribe al disco con debounce (2s de inactividad)."""
    global _registro_pendiente
    config = cargar_configuracion()
    with _registro_lock:
        if tipo == "ficha":
            _registro_pendiente["fichas"] = _registro_pendiente.get("fichas", 0) + cantidad
            _registro_pendiente["dinero"] = _registro_pendiente.get("dinero", 0) + cantidad * config.get("valor_ficha", 1.0)
        elif tipo in ["Promo 1", "Promo 2", "Promo 3"]:
            promos = _registro_pendiente.setdefault("promos", {})
            promos[tipo] = promos.get(tipo, 0) + 1
            _registro_pendiente["dinero"] = _registro_pendiente.get("dinero", 0) + config.get("promociones", {}).get(tipo, {}).get("precio", 0)
    _programar_flush_registro()

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
        response = requests.post(DNSLocal + url, json=datos, timeout=5)
        # print(f"[REPORTE VENTA] Datos de venta enviados. Respuesta: {response.status_code}")
    except requests.RequestException as e:
        print(f"[ERROR REPORTE VENTA] No se pudo enviar el reporte de venta (local): {e}")

    try:
        # Usamos la URL de datos generales para reportar la venta
        response = requests.post(DNS + url, json=datos, timeout=5)
    except requests.RequestException as e:
        print(f"[ERROR REPORTE VENTA] No se pudo enviar el reporte de venta (remoto): {e}")

# --- ENVÍO DE DATOS AL SERVIDOR ---
def enviar_pulso():
    config = cargar_configuracion()
    device_id = config.get("device_id")
    data = {"device_id": device_id}
    try:
        response = requests.post(SERVER_HEARTBEAT, json=data, timeout=5)
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
    - ⚠️ PROTECCIÓN ANTI-QUEMADO: Detiene motor si no dispensa ficha en 2 segundos
    - La GUI lee directamente las variables globales (thread-safe via funciones get)
    """
    global bloqueo_emergencia
    estado_anterior_sensor = GPIO.input(ENTHOPER)
    ficha_en_sensor = False  # Flag para detectar pulso completo
    tiempo_inicio_pulso = 0
    tiempo_inicio_motor = 0  # Marca de tiempo cuando arranca el motor
    motor_con_timeout_activo = False  # Flag para control de timeout

    print("[CORE] Iniciando hilo de control de motor con protección anti-quemado")

    while True:
        # Procesar comandos desde la GUI
        shared_buffer.process_gui_commands()

        # Control del motor basado en fichas_restantes
        if shared_buffer.get_fichas_restantes() > 0 and not bloqueo_emergencia:
            if not shared_buffer.get_motor_activo():
                GPIO.output(MOTOR_PIN, GPIO.HIGH)
                shared_buffer.set_motor_activo(True)
                tiempo_inicio_motor = time.time()  # Iniciar contador de timeout
                motor_con_timeout_activo = True
                print(f"[MOTOR ON] Fichas pendientes: {shared_buffer.get_fichas_restantes()}")
            
            # ⚠️ PROTECCIÓN: Verificar timeout solo si el motor está activo
            elif motor_con_timeout_activo:
                tiempo_motor_activo = time.time() - tiempo_inicio_motor
                if tiempo_motor_activo > TIMEOUT_MOTOR:
                    # Motor trabado - DETENER INMEDIATAMENTE
                    GPIO.output(MOTOR_PIN, GPIO.LOW)
                    shared_buffer.set_motor_activo(False)
                    motor_con_timeout_activo = False
                    bloqueo_emergencia = True  # Bloquear motor hasta confirmación de usuario
                    
                    fichas_pendientes = shared_buffer.get_fichas_restantes()
                    
                    # Alertas críticas
                    print("=" * 60)
                    print("⚠️  [EMERGENCIA - MOTOR TRABADO] ⚠️")
                    print("=" * 60)
                    print(f"Tiempo transcurrido: {tiempo_motor_activo:.1f}s (límite: {TIMEOUT_MOTOR}s)")
                    print(f"Fichas pendientes de dispensar: {fichas_pendientes}")
                    print("ACCIÓN REQUERIDA:")
                    print("  1. REVISAR MECANISMO - Posible atasco o collar enganchado")
                    print("  2. LIBERAR OBSTRUCCIÓN manualmente")
                    print("  3. Presionar botón de expendio nuevamente para reintentar")
                    print(f"  4. Verificar que salgan las {fichas_pendientes} fichas restantes")
                    print("=" * 60)
                    print("IMPORTANTE: Las fichas NO fueron resetadas para evitar")
                    print("            descuadres en el cierre de caja.")
                    print("=" * 60)
                    
                    # NO resetear fichas - mantener el estado para que el cajero pueda corregir
                    # Si el operador arregla el problema o cambia de hopper, puede presionar el botón de nuevo
                    # y el motor intentará dispensar las fichas pendientes
                    
                    # Notificar a la GUI sobre el error crítico
                    if gui_alerta_motor_funcion:
                        try:
                            gui_alerta_motor_funcion(fichas_pendientes)
                        except Exception as e:
                            print(f"[ERROR] GUI alerta motor falló: {e}")
                    
                    # Actualizar GUI normalmente también
                    if gui_actualizar_funcion:
                        try:
                            gui_actualizar_funcion()
                        except Exception as e:
                            print(f"[ERROR] GUI actualizar falló: {e}")
        else:
            if shared_buffer.get_motor_activo():
                GPIO.output(MOTOR_PIN, GPIO.LOW)
                shared_buffer.set_motor_activo(False)
                motor_con_timeout_activo = False
                print("[MOTOR OFF] Todas las fichas expendidas")
                # Enviar reporte en hilo separado para no bloquear el loop del motor
                threading.Thread(target=enviar_datos_venta_servidor, daemon=True).start()

        # Leer estado actual del sensor
        estado_actual_sensor = GPIO.input(ENTHOPER)
        tiempo_actual = time.time()

        # Máquina de estados para detección de pulso completo
        if not ficha_en_sensor:
            # Estado: Esperando ficha (sensor en HIGH)
            if estado_anterior_sensor == GPIO.HIGH and estado_actual_sensor == GPIO.LOW:
                # Flanco descendente detectado - Ficha entrando (CORTADO)
                ficha_en_sensor = True
                tiempo_inicio_pulso = tiempo_actual
                
                # --- CONTAR AL CORTAR (FLANCO DESCENDENTE) ---
                if shared_buffer.get_fichas_restantes() > 0:
                    shared_buffer.decrementar_fichas_restantes()
                    # Resetear timeout del motor para dar tiempo a que salga
                    tiempo_inicio_motor = time.time()
                    print(f"✅ [FICHA DETECTADA - CORTADO] Restantes: {shared_buffer.get_fichas_restantes()}")
                    
                    # Actualizar registro
                    actualizar_registro("ficha", 1)
                    
                    # Notificar a la GUI inmediatamente
                    if gui_actualizar_funcion:
                        try:
                            gui_actualizar_funcion()
                        except Exception as e:
                            print(f"[ERROR] GUI actualizar falló: {e}")
                else:
                    print("[ADVERTENCIA] Sensor activado pero contador en 0")
        else:
            # Estado: Ficha en el sensor (esperando que salga)
            if estado_actual_sensor == GPIO.HIGH:
                # Flanco ascendente - Ficha salió completamente
                duracion_pulso = tiempo_actual - tiempo_inicio_pulso
                ficha_en_sensor = False

                # Solo loguear duración, ya se contó al entrar
                if duracion_pulso < PULSO_MIN:
                    print(f"[RUIDO POSIBLE] Pulso muy corto: {duracion_pulso*1000:.1f}ms (Ya contada)")
                elif duracion_pulso > PULSO_MAX:
                    print(f"[ADVERTENCIA] Pulso muy largo: {duracion_pulso*1000:.1f}ms")

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
    print("Sistema de control de motor iniciado con protección anti-quemado")

    return motor_thread

def detener_sistema():
    """Apaga el motor y limpia GPIO"""
    _flush_registro()  # Asegurar que no queden datos sin guardar
    GPIO.output(MOTOR_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("Sistema detenido")

