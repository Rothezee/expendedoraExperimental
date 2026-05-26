import atexit
import time
import threading
import json
import os
from datetime import datetime
import shared_buffer
from infra.config_repository import ConfigRepository
from infra.machine_limits import MAX_MACHINE_HOPPERS
from infra.state_store import atomic_write_json, get_recovered_counters, recover_state, save_snapshot, build_snapshot, load_snapshot
from infra.telemetry_client import TelemetryClient

# PERSISTENCIA EN EJECUCION: este archivo se relee/guarda durante runtime.
# Si queres que los pines queden permanentes, modifica config.json.
config_file = "config.json"
registro_file = "registro.json"
_config_repository = ConfigRepository(config_file)
_telemetry_client = TelemetryClient(_config_repository)

# --- ESCRITURA A DISCO CON DEBOUNCE ---
# Evita escribir registro.json en cada ficha.
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
            atomic_write_json(registro_file, registro)
            print(f"[REGISTRO] Guardado: +{_registro_pendiente.get('fichas',0)} fichas, +{_registro_pendiente.get('dinero',0):.2f} dinero")
            _registro_pendiente = {}
        _registro_timer = None

def _programar_flush_registro():
    """Compat: flush inmediato (sin debounce) para no perder datos en cortes."""
    _flush_registro()

_recovered_state: dict | None = None

# --- CONFIGURACIÓN DE TOLVAS ---
DEFAULT_TOLVAS = [
    {
        "id": 1,
        "nombre": "Tolva 1",
        "motor_pin": 13,
        "motor_pin_rev": 11,
        "sensor_pin": 9,
        "calibracion": {"pulso_min_s": 0.05, "pulso_max_s": 0.5, "timeout_motor_s": 2.0},
    },
]

# --- CONFIGURACIÓN DEL SENSOR ---
PULSO_MIN = 0.05  # Duración mínima del pulso (50ms) - filtro de ruido
PULSO_MAX = 0.5   # Duración máxima del pulso (500ms) - filtro de bloqueos
DEFAULT_SENSOR_BOUNCETIME_MS = 8

# --- CONFIGURACIÓN DE PROTECCIÓN DEL MOTOR ---
TIMEOUT_MOTOR = 2.0  # 2 segundos máximo sin dispensar ficha (PROTECCIÓN ANTI-QUEMADO)

DEFAULT_HEARTBEAT_INTERVALO_S = 600  # 10 minutos

# --- CALLBACK SIMPLE PARA NOTIFICAR CAMBIOS ---
gui_actualizar_funcion = None  # Función simple que actualiza la GUI cuando cambian los contadores
gui_alerta_motor_funcion = None  # Función para alertar sobre motor trabado

# --- DESTRABE (RETROCESO / INVERSIÓN) ---
DEFAULT_DESTRABE_ENABLED = True
DEFAULT_DESTRABE_AUTO_ON_TIMEOUT = True
DEFAULT_DESTRABE_RETROCESO_S = 1.5
DEFAULT_DESTRABE_MAX_INTENTOS = 1
DEFAULT_DESTRABE_COOLDOWN_S = 2.0

_destrabe_request_lock = threading.Lock()
_destrabe_requested = {"tolva_id": None, "ts": 0.0}

# Por defecto, asumimos módulos de relé "active LOW" (común en placas de relés):
# - OFF = HIGH
# - ON  = LOW
# Se puede overridear por tolva con "motor_active_low": false en config.
DEFAULT_MOTOR_ACTIVE_LOW = True

# Variable global para controlar el bloqueo por emergencia
bloqueo_emergencia = False
_tolvas_lock = threading.Lock()
_tolvas = list(DEFAULT_TOLVAS)
_tolva_seleccionada_idx = 0
_tolvas_trabadas = set()
_sensor_interrupts_cfg = {"bouncetime_ms": DEFAULT_SENSOR_BOUNCETIME_MS}
_esp32_bridge = None

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


def solicitar_destrabe(tolva_id=None):
    """
    Solicita un destrabe manual (retroceso) para una tolva.
    Si tolva_id es None, usa la tolva seleccionada actualmente.
    """
    global _destrabe_requested
    try:
        tolva_id_int = int(tolva_id) if tolva_id is not None else None
    except (TypeError, ValueError):
        tolva_id_int = None
    with _destrabe_request_lock:
        _destrabe_requested = {"tolva_id": tolva_id_int, "ts": time.time()}
    print(f"[CORE] Solicitud de destrabe recibida (tolva_id={tolva_id_int})")


def _cargar_tolvas_desde_config():
    global _tolvas, _sensor_interrupts_cfg
    cfg = cargar_configuracion()
    machine = cfg.get("maquina", {})
    interrupts_cfg = machine.get("sensor_interrupts", {}) if isinstance(machine.get("sensor_interrupts", {}), dict) else {}
    try:
        bouncetime_ms = int(float(interrupts_cfg.get("bouncetime_ms", DEFAULT_SENSOR_BOUNCETIME_MS)))
    except (TypeError, ValueError):
        bouncetime_ms = DEFAULT_SENSOR_BOUNCETIME_MS
    _sensor_interrupts_cfg = {"bouncetime_ms": max(0, min(1000, bouncetime_ms))}
    hoppers = machine.get("hoppers", DEFAULT_TOLVAS)
    if not isinstance(hoppers, list) or not hoppers:
        hoppers = list(DEFAULT_TOLVAS)
    normalized = []
    for idx, hopper in enumerate(hoppers[:MAX_MACHINE_HOPPERS], start=1):
        if not isinstance(hopper, dict):
            hopper = {}
        fallback = DEFAULT_TOLVAS[(idx - 1) % len(DEFAULT_TOLVAS)]
        normalized.append(
            {
                "id": int(hopper.get("id", fallback["id"])),
                "nombre": str(hopper.get("nombre", fallback["nombre"])),
                "motor_pin": int(hopper.get("motor_pin", fallback["motor_pin"])),
                "motor_pin_rev": (
                    int(hopper.get("motor_pin_rev"))
                    if hopper.get("motor_pin_rev") is not None and str(hopper.get("motor_pin_rev")).strip() != ""
                    else None
                ),
                "motor_active_low": bool(hopper.get("motor_active_low", DEFAULT_MOTOR_ACTIVE_LOW)),
                "sensor_pin": int(hopper.get("sensor_pin", fallback["sensor_pin"])),
                "sensor_bouncetime_ms": (
                    int(float(hopper.get("sensor_bouncetime_ms", _sensor_interrupts_cfg["bouncetime_ms"])))
                    if str(hopper.get("sensor_bouncetime_ms", "")).strip() != ""
                    else _sensor_interrupts_cfg["bouncetime_ms"]
                ),
                "calibracion": dict(
                    hopper.get("calibracion", fallback.get("calibracion", {}))
                    if isinstance(hopper.get("calibracion", {}), dict)
                    else fallback.get("calibracion", {})
                ),
                "destrabe": dict(hopper.get("destrabe", {})) if isinstance(hopper.get("destrabe", {}), dict) else {},
            }
        )
    with _tolvas_lock:
        _tolvas = normalized


def inject_sensor_pulse_events(pin=None):
    """Simula un TOKEN (MCU conectado o fallback local en PC)."""
    from infra.esp32_bridge import get_bridge

    bridge = get_bridge()
    if bridge is None:
        print("[CORE] SIMULATE: puente no iniciado")
        return False
    ok = bridge.simulate_token()
    if not ok:
        print("[CORE] SIMULATE: sin fichas pendientes")
    return ok


def esp32_is_connected():
    from infra.esp32_bridge import bridge_is_ready

    return bridge_is_ready()


def recargar_tolvas_desde_config():
    """Recarga configuración de tolvas/calibración en caliente y reenvía CONFIG al ESP32."""
    _cargar_tolvas_desde_config()
    if _esp32_bridge is not None and _esp32_bridge.is_ready():
        config = cargar_configuracion()
        with _tolvas_lock:
            idx = _tolva_seleccionada_idx
            tolva = dict(_tolvas[idx]) if _tolvas else {}
        from infra.esp32_protocol import destrabe_from_config, hopper_from_tolva

        _esp32_bridge.backend.configure_hopper(
            hopper_from_tolva(tolva),
            destrabe_from_config(config, tolva),
        )


def get_tolvas_status():
    with _tolvas_lock:
        selected_id = _tolvas[_tolva_seleccionada_idx]["id"]
        jammed_ids = set(_tolvas_trabadas)
        return [
            {
                "id": tolva["id"],
                "nombre": tolva["nombre"],
                "seleccionada": tolva["id"] == selected_id,
                "trabada": tolva["id"] in jammed_ids,
            }
            for tolva in _tolvas
        ]


def seleccionar_tolva(offset):
    global _tolva_seleccionada_idx
    with _tolvas_lock:
        _tolva_seleccionada_idx = (_tolva_seleccionada_idx + offset) % len(_tolvas)
    if gui_actualizar_funcion:
        try:
            gui_actualizar_funcion()
        except Exception as exc:
            print(f"[ERROR] GUI actualizar al cambiar tolva: {exc}")


def seleccionar_tolva_siguiente():
    seleccionar_tolva(1)


def seleccionar_tolva_anterior():
    seleccionar_tolva(-1)


# ----------CONEXION CON GUI Y LOGICA PARA GUARDAR REGISTROS---------------

def cargar_configuracion():
    return _config_repository.load()

def guardar_configuracion(config):
    _config_repository.save(config)

def recuperar_y_hidratar_estado():
    """
    Fusiona machine_state + fuentes legacy y hidrata shared_buffer.
    """
    global _recovered_state
    try:
        snapshot = recover_state(
            config_path=config_file,
            buffer_path=shared_buffer.STATE_FILE,
            registro_path=registro_file,
        )
        _recovered_state = get_recovered_counters(snapshot)
        buf = _recovered_state["buffer"]
        shared_buffer.hydrate_from_recovery(buf)
        shared_buffer.register_gui_counters(
            _recovered_state["contadores_global"],
            _recovered_state["contadores_global"],
            _recovered_state["contadores_parcial"],
        )
        cnt = _recovered_state["contadores_global"]
        print(
            "[CORE] Estado recuperado: "
            f"fichas_total={cnt.get('fichas_expendidas', 0)}, "
            f"restantes={cnt.get('fichas_restantes', 0)}, "
            f"dinero={cnt.get('dinero_ingresado', 0)}"
        )
        return _recovered_state
    except Exception as exc:
        print(f"[CORE] No se pudo recuperar estado: {exc}")
        _recovered_state = None
        return None


def get_recovered_state():
    return _recovered_state


def hidratar_estado_compartido_desde_config():
    """Compat: delega en recuperación unificada."""
    return recuperar_y_hidratar_estado()

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
    atomic_write_json(registro_file, registro)

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

def enviar_datos_venta_servidor():
    """
    NOTA: Esta función se llama cuando el motor se detiene o por TOKEN.
        Aquí se envía el acumulado de la sesión activa (se reinicia al cerrar sesión).
    """

    config = cargar_configuracion()
    datos = _telemetry_client.build_telemetry_body(
        config,
        fichas=shared_buffer.get_fichas_expendidas(),
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

# --- PROGRAMA PRINCIPAL ---
def iniciar_sistema():
    """Inicializa el puente ESP32 (motor/sensor en el microcontrolador)."""
    global _esp32_bridge

    _cargar_tolvas_desde_config()
    recuperar_y_hidratar_estado()
    enviar_pulso()

    import sys
    from infra.esp32_bridge import Esp32Bridge, set_bridge

    _esp32_bridge = Esp32Bridge(sys.modules[__name__])
    set_bridge(_esp32_bridge)
    if not _esp32_bridge.start():
        print("[CORE] ESP32 no conectado al inicio; el puente reintentará en segundo plano")
    motor_thread = threading.Thread(target=_esp32_bridge.run_loop, daemon=True)
    motor_thread.start()
    print("[CORE] Sistema iniciado (ESP32 serial USB)")
    return motor_thread


def _flush_persistencia_final():
    shared_buffer.flush_pending()
    _flush_registro()
    try:
        snap = load_snapshot()
        if snap:
            save_snapshot(snap, sync_config=cargar_configuracion(), config_path=config_file)
    except Exception as exc:
        print(f"[CORE] Aviso persistiendo estado final: {exc}")


def detener_sistema():
    """Detiene el puente ESP32 y apaga el motor vía serial."""
    global _esp32_bridge
    _flush_persistencia_final()
    if _esp32_bridge is not None:
        _esp32_bridge.stop()
        from infra.esp32_bridge import set_bridge

        set_bridge(None)
        _esp32_bridge = None
    print("[CORE] Sistema detenido")


class CoreController:
    """
    Fachada OO del módulo core para inyección en GUI/main.
    Mantiene compatibilidad con la lógica actual basada en funciones.
    """

    @property
    def sensor_pin(self):
        with _tolvas_lock:
            return _tolvas[_tolva_seleccionada_idx]["sensor_pin"]

    def simulate_sensor_pulse(self, pin=None):
        """Simula una ficha dispensada (MCU o fallback PC)."""
        return inject_sensor_pulse_events(pin=pin)

    def get_tolvas_status(self):
        return get_tolvas_status()

    def seleccionar_tolva_siguiente(self):
        seleccionar_tolva_siguiente()

    def seleccionar_tolva_anterior(self):
        seleccionar_tolva_anterior()

    def recargar_tolvas_desde_config(self):
        recargar_tolvas_desde_config()

    def register_gui_update(self, callback):
        registrar_gui_actualizar(callback)

    def register_gui_motor_alert(self, callback):
        registrar_gui_alerta_motor(callback)

    def unlock_motor(self):
        desbloquear_motor()

    def request_unjam(self, tolva_id=None):
        solicitar_destrabe(tolva_id=tolva_id)

    def get_recovered_state(self):
        return get_recovered_state()

    def start(self):
        return iniciar_sistema()

    def stop(self):
        detener_sistema()


def _atexit_persist():
    try:
        _flush_persistencia_final()
    except Exception:
        pass


atexit.register(_atexit_persist)