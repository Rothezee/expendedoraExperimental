from gpio_sim import GPIO #import RPi.GPIO as GPIO  # Descomentar para usar en hardware real#
import time
import threading
import json
import os
from datetime import datetime
import shared_buffer
from infra.config_repository import ConfigRepository
from infra.telemetry_client import TelemetryClient

config_file = "config.json"
registro_file = "registro.json"
_config_repository = ConfigRepository(config_file)
_telemetry_client = TelemetryClient(_config_repository)

# --- ESCRITURA A DISCO CON DEBOUNCE ---
# Evita escribir registro.json en cada ficha (costoso en SD card).
# Acumula cambios y escribe UNA sola vez después de 2 segundos de inactividad.
_registro_pendiente = {}
_registro_lock = threading.Lock()
_registro_timer = None

#GPIO.setwarnings(False) descomentar para usar en hardware real

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

# --- CONFIGURACIÓN DE PINES ---
MOTOR_PIN = 24  # Pin del motor
ENTHOPER = 16  # Sensor para contar fichas que salen

# --- CONFIGURACIÓN DEL SENSOR ---
PULSO_MIN = 0.05  # Duración mínima del pulso (50ms) - filtro de ruido
PULSO_MAX = 0.5   # Duración máxima del pulso (500ms) - filtro de bloqueos

# --- CONFIGURACIÓN DE PROTECCIÓN DEL MOTOR ---
TIMEOUT_MOTOR = 2.0  # 2 segundos máximo sin dispensar ficha (PROTECCIÓN ANTI-QUEMADO)

DEFAULT_HEARTBEAT_INTERVALO_S = 600  # 10 minutos

# --- CALLBACK SIMPLE PARA NOTIFICAR CAMBIOS ---
gui_actualizar_funcion = None  # Función simple que actualiza la GUI cuando cambian los contadores
gui_alerta_motor_funcion = None  # Función para alertar sobre motor trabado

# Variable global para controlar el bloqueo por emergencia
bloqueo_emergencia = False

def registrar_gui_actualizar(funcion):
    """Registra la función de actualización de la GUI"""
    global gui_actualizar_funcion
    gui_actualizar_funcion = funcion

def registrar_gui_alerta_motor(funcion):
    """Registra la función de alerta de motor trabado para la GUI"""
    global gui_alerta_motor_funcion
    gui_alerta_motor_funcion = funcion

def desbloquear_motor():
    """Permite reanudar el motor después de un bloqueo por timeout"""
    global bloqueo_emergencia
    bloqueo_emergencia = False
    print("[CORE] Motor desbloqueado por usuario, reanudando operación...")

# ----------CONEXION CON GUI Y LOGICA PARA GUARDAR REGISTROS---------------

def cargar_configuracion():
    return _config_repository.load()

def guardar_configuracion(config):
    _config_repository.save(config)

def hidratar_estado_compartido_desde_config():
    """
    Recupera contadores críticos desde config para evitar reset a 0
    tras cortes de energía y sincronizar telemetría.
    """
    try:
        config = cargar_configuracion()
        contadores = config.get("contadores", {})
        shared_buffer.set_fichas_restantes(int(contadores.get("fichas_restantes", 0)))
        shared_buffer.set_fichas_expendidas(int(contadores.get("fichas_expendidas", 0)))
        shared_buffer.set_r_cuenta(float(contadores.get("dinero_ingresado", 0)))
        print(
            "[CORE] Estado recuperado desde config: "
            f"fichas_total={contadores.get('fichas_expendidas', 0)}, "
            f"dinero={contadores.get('dinero_ingresado', 0)}"
        )
    except Exception as exc:
        print(f"[CORE] No se pudo hidratar estado desde config: {exc}")

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

def enviar_datos_venta_servidor():
    """
    NOTA: Esta función se llama cuando el motor se detiene.
        Aquí se deben obtener los datos relevantes de la venta que acaba de terminar.
        Enviamos el contador TOTAL para el servidor, no el de sesión.
    """

    config = cargar_configuracion()
    datos = _telemetry_client.build_telemetry_body(
        config,
        fichas=shared_buffer.get_fichas_expendidas_total(),
        dinero=shared_buffer.get_r_cuenta(),
    )
    _telemetry_client.post_body(datos, "telemetria")

# --- ENVÍO DE DATOS AL SERVIDOR ---
def enviar_pulso():
    config = cargar_configuracion()
    data = _telemetry_client.build_heartbeat_body(config)
    _telemetry_client.post_body(data, "heartbeat")

    intervalo = config.get("heartbeat", {}).get("intervalo_s", DEFAULT_HEARTBEAT_INTERVALO_S)
    heartbeat_timer = threading.Timer(intervalo, enviar_pulso)
    heartbeat_timer.daemon = True
    heartbeat_timer.start()

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
      try:
        # Procesar comandos desde la GUI
        shared_buffer.process_gui_commands()

        # Control del motor basado en fichas_restantes
        if shared_buffer.get_fichas_restantes() > 0 and not bloqueo_emergencia:
            if not shared_buffer.get_motor_activo():
                GPIO.output(MOTOR_PIN, GPIO.HIGH)
                shared_buffer.set_motor_activo(True)
                tiempo_inicio_motor = time.time()
                motor_con_timeout_activo = True
                print(f"[MOTOR ON] Fichas pendientes: {shared_buffer.get_fichas_restantes()}")
            
            elif motor_con_timeout_activo:
                tiempo_motor_activo = time.time() - tiempo_inicio_motor
                if tiempo_motor_activo > TIMEOUT_MOTOR:
                    GPIO.output(MOTOR_PIN, GPIO.LOW)
                    shared_buffer.set_motor_activo(False)
                    motor_con_timeout_activo = False
                    bloqueo_emergencia = True

                    fichas_pendientes = shared_buffer.get_fichas_restantes()
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

                    if gui_alerta_motor_funcion:
                        try:
                            gui_alerta_motor_funcion(fichas_pendientes)
                        except Exception as e:
                            print(f"[ERROR] GUI alerta motor falló: {e}")

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
                threading.Thread(target=enviar_datos_venta_servidor, daemon=True).start()

        # Leer estado actual del sensor
        estado_actual_sensor = GPIO.input(ENTHOPER)
        tiempo_actual = time.time()

        # Máquina de estados para detección de pulso completo
        if not ficha_en_sensor:
            if estado_anterior_sensor == GPIO.HIGH and estado_actual_sensor == GPIO.LOW:
                ficha_en_sensor = True
                tiempo_inicio_pulso = tiempo_actual

                if shared_buffer.get_fichas_restantes() > 0:
                    shared_buffer.decrementar_fichas_restantes()
                    tiempo_inicio_motor = time.time()
                    print(f"✅ [FICHA DETECTADA - CORTADO] Restantes: {shared_buffer.get_fichas_restantes()}")

                    try:
                        actualizar_registro("ficha", 1)
                    except Exception as e:
                        print(f"[ERROR] actualizar_registro falló (motor continúa): {e}")

                    if gui_actualizar_funcion:
                        try:
                            gui_actualizar_funcion()
                        except Exception as e:
                            print(f"[ERROR] GUI actualizar falló: {e}")
                else:
                    print("[ADVERTENCIA] Sensor activado pero contador en 0")
        else:
            if estado_actual_sensor == GPIO.HIGH:
                duracion_pulso = tiempo_actual - tiempo_inicio_pulso
                ficha_en_sensor = False

                if duracion_pulso < PULSO_MIN:
                    print(f"[RUIDO POSIBLE] Pulso muy corto: {duracion_pulso*1000:.1f}ms (Ya contada)")
                elif duracion_pulso > PULSO_MAX:
                    print(f"[ADVERTENCIA] Pulso muy largo: {duracion_pulso*1000:.1f}ms")

        estado_anterior_sensor = estado_actual_sensor
        time.sleep(0.005)

      except Exception as e:
        # El loop del motor NUNCA debe morir. Cualquier excepción se loga y se continúa.
        print(f"[MOTOR LOOP ERROR - CONTINUANDO] {type(e).__name__}: {e}")
        try:
            GPIO.output(MOTOR_PIN, GPIO.LOW)
            shared_buffer.set_motor_activo(False)
        except:
            pass
        time.sleep(0.1)

# --- PROGRAMA PRINCIPAL ---
def iniciar_sistema():
    """Inicializa el sistema de control de motor (sin GUI)"""
    hidratar_estado_compartido_desde_config()
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


class CoreController:
    """
    Fachada OO del módulo core para inyección en GUI/main.
    Mantiene compatibilidad con la lógica actual basada en funciones.
    """

    sensor_pin = ENTHOPER

    def register_gui_update(self, callback):
        registrar_gui_actualizar(callback)

    def register_gui_motor_alert(self, callback):
        registrar_gui_alerta_motor(callback)

    def unlock_motor(self):
        desbloquear_motor()

    def start(self):
        return iniciar_sistema()

    def stop(self):
        detener_sistema()