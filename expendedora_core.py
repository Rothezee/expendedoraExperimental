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

# --- CONFIGURACIÓN DE TOLVAS ---
DEFAULT_TOLVAS = [
    {
        "id": 1,
        "nombre": "Tolva 1",
        "motor_pin": 24,
        "sensor_pin": 16,
        "calibracion": {"pulso_min_s": 0.05, "pulso_max_s": 0.5, "timeout_motor_s": 2.0},
    },
    {
        "id": 2,
        "nombre": "Tolva 2",
        "motor_pin": 25,
        "sensor_pin": 17,
        "calibracion": {"pulso_min_s": 0.05, "pulso_max_s": 0.5, "timeout_motor_s": 2.0},
    },
    {
        "id": 3,
        "nombre": "Tolva 3",
        "motor_pin": 23,
        "sensor_pin": 27,
        "calibracion": {"pulso_min_s": 0.05, "pulso_max_s": 0.5, "timeout_motor_s": 2.0},
    },
]

# --- CONFIGURACIÓN DEL SENSOR ---
PULSO_MIN = 0.05  # Duración mínima del pulso (50ms) - filtro de ruido
PULSO_MAX = 0.5   # Duración máxima del pulso (500ms) - filtro de bloqueos

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

_motor_io_lock = threading.Lock()
_destrabe_request_lock = threading.Lock()
_destrabe_requested = {"tolva_id": None, "ts": 0.0}

# Variable global para controlar el bloqueo por emergencia
bloqueo_emergencia = False
_tolvas_lock = threading.Lock()
_tolvas = list(DEFAULT_TOLVAS)
_tolva_seleccionada_idx = 0
_tolvas_trabadas = set()
_ultima_tolva_motor_idx = None
_ultimo_apagado_motor_ts = 0.0
_ventana_pulso_tardio_por_tolva = {}
_auto_calibration = {
    "running": False,
    "finished": False,
    "target_tolva_id": None,
    "target_samples": 0,
    "counted_samples": 0,
    "total_counted_samples": 0,
    "rounds_total": 1,
    "current_round": 1,
    "round_results": [],
    "first_pulse_delays": [],
    "pulse_durations": [],
    "motor_on_ts": None,
    "pulse_open_ts": None,
    "start_ts": 0.0,
    "max_duration_s": 45.0,
    "error": "",
    "result": {},
}

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
    global _tolvas, _ventana_pulso_tardio_por_tolva
    cfg = cargar_configuracion()
    machine = cfg.get("maquina", {})
    hoppers = machine.get("hoppers", DEFAULT_TOLVAS)
    if not isinstance(hoppers, list) or not hoppers:
        hoppers = list(DEFAULT_TOLVAS)
    normalized = []
    for idx, hopper in enumerate(hoppers[:3], start=1):
        if not isinstance(hopper, dict):
            hopper = {}
        fallback = DEFAULT_TOLVAS[idx - 1]
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
                "sensor_pin": int(hopper.get("sensor_pin", fallback["sensor_pin"])),
                "calibracion": dict(
                    hopper.get("calibracion", fallback.get("calibracion", {}))
                    if isinstance(hopper.get("calibracion", {}), dict)
                    else fallback.get("calibracion", {})
                ),
                "destrabe": dict(hopper.get("destrabe", {})) if isinstance(hopper.get("destrabe", {}), dict) else {},
            }
        )
    while len(normalized) < 3:
        normalized.append(dict(DEFAULT_TOLVAS[len(normalized)]))
    with _tolvas_lock:
        _tolvas = normalized
        _ventana_pulso_tardio_por_tolva = {}
        for idx, tolva in enumerate(_tolvas):
            pulso_min, pulso_max, _ = _calibracion_tolva(tolva)
            _ventana_pulso_tardio_por_tolva[idx] = max(0.15, min(2.0, pulso_max + pulso_min))


def _calibracion_tolva(tolva):
    calibracion = tolva.get("calibracion", {})
    if not isinstance(calibracion, dict):
        calibracion = {}
    try:
        pulso_min = float(calibracion.get("pulso_min_s", PULSO_MIN))
    except (TypeError, ValueError):
        pulso_min = PULSO_MIN
    try:
        pulso_max = float(calibracion.get("pulso_max_s", PULSO_MAX))
    except (TypeError, ValueError):
        pulso_max = PULSO_MAX
    try:
        timeout_motor = float(calibracion.get("timeout_motor_s", TIMEOUT_MOTOR))
    except (TypeError, ValueError):
        timeout_motor = TIMEOUT_MOTOR
    pulso_min = max(pulso_min, 0.001)
    pulso_max = max(pulso_max, pulso_min)
    timeout_motor = max(timeout_motor, 0.1)
    return pulso_min, pulso_max, timeout_motor


def _actualizar_auto_calibracion_tardia(tolva_idx, delay_s):
    """
    Ajusta automáticamente la ventana de pulso tardío para una tolva
    según el retardo real observado luego del corte del motor.
    """
    if tolva_idx is None:
        return
    with _tolvas_lock:
        actual = float(_ventana_pulso_tardio_por_tolva.get(tolva_idx, 0.3))
        sugerida = max(0.15, min(2.0, delay_s * 1.35))
        if sugerida > actual:
            _ventana_pulso_tardio_por_tolva[tolva_idx] = sugerida
        else:
            # convergencia suave para no crecer indefinidamente
            _ventana_pulso_tardio_por_tolva[tolva_idx] = max(0.15, (actual * 0.98) + (sugerida * 0.02))


def _setup_gpio_tolvas():
    GPIO.setmode(GPIO.BCM)
    for tolva in _tolvas:
        GPIO.setup(tolva["sensor_pin"], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(tolva["motor_pin"], GPIO.OUT)
        GPIO.output(tolva["motor_pin"], GPIO.LOW)
        motor_rev = tolva.get("motor_pin_rev")
        if motor_rev:
            GPIO.setup(int(motor_rev), GPIO.OUT)
            GPIO.output(int(motor_rev), GPIO.LOW)


def _motor_set(tolva, mode):
    """
    mode: 'off' | 'fwd' | 'rev'
    Con 2 relés: motor_pin = adelante, motor_pin_rev = reversa.
    """
    fwd = int(tolva["motor_pin"])
    rev = tolva.get("motor_pin_rev")
    rev = int(rev) if rev else None
    with _motor_io_lock:
        if mode == "off":
            GPIO.output(fwd, GPIO.LOW)
            if rev:
                GPIO.output(rev, GPIO.LOW)
            return
        if mode == "fwd":
            if rev:
                GPIO.output(rev, GPIO.LOW)
            GPIO.output(fwd, GPIO.HIGH)
            return
        if mode == "rev":
            if not rev:
                GPIO.output(fwd, GPIO.LOW)
                return
            GPIO.output(fwd, GPIO.LOW)
            GPIO.output(rev, GPIO.HIGH)
            return


def _motor_off_all(tolvas_local):
    for t in tolvas_local:
        _motor_set(t, "off")


def _get_destrabe_cfg(selected_tolva, cfg):
    machine = cfg.get("maquina", {}) if isinstance(cfg.get("maquina", {}), dict) else {}
    base = machine.get("destrabe", {}) if isinstance(machine.get("destrabe", {}), dict) else {}
    per_tolva = selected_tolva.get("destrabe", {}) if isinstance(selected_tolva.get("destrabe", {}), dict) else {}
    enabled = bool(per_tolva.get("enabled", base.get("enabled", DEFAULT_DESTRABE_ENABLED)))
    auto_on_timeout = bool(per_tolva.get("auto_on_timeout", base.get("auto_on_timeout", DEFAULT_DESTRABE_AUTO_ON_TIMEOUT)))
    try:
        retroceso_s = float(per_tolva.get("retroceso_s", base.get("retroceso_s", DEFAULT_DESTRABE_RETROCESO_S)))
    except (TypeError, ValueError):
        retroceso_s = DEFAULT_DESTRABE_RETROCESO_S
    try:
        max_intentos = int(per_tolva.get("max_intentos", base.get("max_intentos", DEFAULT_DESTRABE_MAX_INTENTOS)))
    except (TypeError, ValueError):
        max_intentos = DEFAULT_DESTRABE_MAX_INTENTOS
    try:
        cooldown_s = float(per_tolva.get("cooldown_s", base.get("cooldown_s", DEFAULT_DESTRABE_COOLDOWN_S)))
    except (TypeError, ValueError):
        cooldown_s = DEFAULT_DESTRABE_COOLDOWN_S
    retroceso_s = max(0.0, min(10.0, retroceso_s))
    max_intentos = max(0, min(10, max_intentos))
    cooldown_s = max(0.0, min(30.0, cooldown_s))
    return {
        "enabled": enabled,
        "auto_on_timeout": auto_on_timeout,
        "retroceso_s": retroceso_s,
        "max_intentos": max_intentos,
        "cooldown_s": cooldown_s,
    }


def _hacer_retroceso_en_hilo(tolva, dur_s):
    def _run():
        nombre = tolva.get("nombre", "Tolva")
        print(f"[DESTRABE] Retroceso {dur_s:.2f}s en {nombre}")
        _motor_set(tolva, "rev")
        time.sleep(dur_s)
        _motor_set(tolva, "off")
        print(f"[DESTRABE] Fin retroceso en {nombre}")
    threading.Thread(target=_run, daemon=True).start()


def recargar_tolvas_desde_config():
    """Recarga configuración de tolvas/calibración en caliente."""
    _cargar_tolvas_desde_config()


def iniciar_auto_calibracion_tolva(tolva_id, samples=32):
    """
    Inicia auto-calibración para una tolva:
    - agrega fichas pendientes para forzar dispensado
    - mide delay de salida y duración de pulsos
    - persiste calibración calculada en config
    """
    global _tolva_seleccionada_idx
    try:
        target_samples = max(3, int(samples))
    except (TypeError, ValueError):
        target_samples = 32

    with _tolvas_lock:
        if _auto_calibration.get("running"):
            return False, "Ya hay una auto-calibración en curso."
        if shared_buffer.get_fichas_restantes() > 0 or shared_buffer.get_motor_activo():
            return False, "Esperá a que termine la dispensación actual para calibrar."
        idx = next((i for i, t in enumerate(_tolvas) if t["id"] == tolva_id), None)
        if idx is None:
            return False, "Tolva no encontrada."

        _tolva_seleccionada_idx = idx
        _auto_calibration.update(
            {
                "running": True,
                "finished": False,
                "target_tolva_id": tolva_id,
                "target_samples": target_samples,
                "counted_samples": 0,
                "total_counted_samples": 0,
                "rounds_total": 1,
                "current_round": 1,
                "round_results": [],
                "first_pulse_delays": [],
                "pulse_durations": [],
                "motor_on_ts": None,
                "pulse_open_ts": None,
                "start_ts": time.time(),
                "max_duration_s": 45.0,
                "error": "",
                "result": {},
            }
        )

    shared_buffer.agregar_fichas(target_samples)
    if gui_actualizar_funcion:
        try:
            gui_actualizar_funcion()
        except Exception:
            pass
    return True, f"Auto-calibración iniciada para tolva {tolva_id} con {target_samples} fichas."


def _finalizar_auto_calibracion(success=True, error_msg=""):
    continuar_siguiente_ronda = False
    fichas_a_agregar = 0
    with _tolvas_lock:
        tolva_id = _auto_calibration.get("target_tolva_id")
        delays = list(_auto_calibration.get("first_pulse_delays", []))
        durations = list(_auto_calibration.get("pulse_durations", []))
        idx = next((i for i, t in enumerate(_tolvas) if t["id"] == tolva_id), None)

        if not success or idx is None or not durations:
            _auto_calibration.update(
                {
                    "running": False,
                    "finished": True,
                    "error": error_msg or "No se pudieron medir pulsos suficientes.",
                    "result": {},
                }
            )
            return

        min_d = min(durations)
        max_d = max(durations)
        max_delay = max(delays) if delays else max_d
        pulso_min_s = max(0.01, min_d * 0.8)
        pulso_max_s = max(pulso_min_s + 0.01, max_d * 1.30)
        timeout_motor_s = max(0.4, max_delay * 2.2)
        result = {
            "pulso_min_s": round(pulso_min_s, 4),
            "pulso_max_s": round(pulso_max_s, 4),
            "timeout_motor_s": round(timeout_motor_s, 4),
            "samples": len(durations),
        }
        _auto_calibration.setdefault("round_results", []).append(dict(result))

        current_round = int(_auto_calibration.get("current_round", 1))
        rounds_total = int(_auto_calibration.get("rounds_total", 1))
        target_samples = int(_auto_calibration.get("target_samples", 0))
        if current_round < rounds_total:
            _auto_calibration.update(
                {
                    "current_round": current_round + 1,
                    "counted_samples": 0,
                    "first_pulse_delays": [],
                    "pulse_durations": [],
                    "motor_on_ts": None,
                    "pulse_open_ts": None,
                    "start_ts": time.time(),
                    "error": "",
                    "result": {
                        "ronda_completada": current_round,
                        "rondas_totales": rounds_total,
                        **result,
                    },
                }
            )
            continuar_siguiente_ronda = True
            fichas_a_agregar = max(0, target_samples)

    if continuar_siguiente_ronda:
        if fichas_a_agregar > 0:
            shared_buffer.agregar_fichas(fichas_a_agregar)
        return

    with _tolvas_lock:
        rounds = _auto_calibration.get("round_results", [])
        if rounds:
            avg_min = sum(float(r.get("pulso_min_s", 0.0)) for r in rounds) / len(rounds)
            avg_max = sum(float(r.get("pulso_max_s", 0.0)) for r in rounds) / len(rounds)
            avg_timeout = sum(float(r.get("timeout_motor_s", 0.0)) for r in rounds) / len(rounds)
            total_samples = sum(int(r.get("samples", 0)) for r in rounds)
            result = {
                "pulso_min_s": round(max(0.01, avg_min), 4),
                "pulso_max_s": round(max(max(0.01, avg_min), avg_max), 4),
                "timeout_motor_s": round(max(0.4, avg_timeout), 4),
                "samples": total_samples,
                "rounds": len(rounds),
            }

        # Aplica en memoria
        calibracion = _tolvas[idx].setdefault("calibracion", {})
        calibracion.update(result)
        _ventana_pulso_tardio_por_tolva[idx] = max(0.15, min(2.0, result["pulso_max_s"] + result["pulso_min_s"]))

    # Persiste en config fuera del lock
    try:
        cfg = cargar_configuracion()
        hoppers = cfg.get("maquina", {}).get("hoppers", [])
        for hopper in hoppers:
            if isinstance(hopper, dict) and int(hopper.get("id", 0)) == int(tolva_id):
                cal = hopper.get("calibracion", {})
                if not isinstance(cal, dict):
                    cal = {}
                cal.update(result)
                hopper["calibracion"] = cal
                break
        guardar_configuracion(cfg)
    except Exception as exc:
        error_msg = f"Calibró en memoria pero falló guardado: {exc}"

    with _tolvas_lock:
        _auto_calibration.update(
            {
                "running": False,
                "finished": True,
                "error": error_msg,
                "result": result,
            }
        )


def get_auto_calibration_status():
    with _tolvas_lock:
        return dict(_auto_calibration)


def get_tolvas_status():
    with _tolvas_lock:
        selected_id = _tolvas[_tolva_seleccionada_idx]["id"]
        jammed_ids = set(_tolvas_trabadas)
        calib = dict(_auto_calibration)
        snapshot = []
        for tolva in _tolvas:
            running_here = bool(calib.get("running") and calib.get("target_tolva_id") == tolva["id"])
            progress = 0
            if running_here and calib.get("target_samples", 0):
                total_target = max(1, int(calib.get("target_samples", 0)) * max(1, int(calib.get("rounds_total", 1))))
                total_done = int(calib.get("total_counted_samples", 0))
                progress = int((total_done * 100) / total_target)
            snapshot.append(
                {
                    "id": tolva["id"],
                    "nombre": tolva["nombre"],
                    "seleccionada": tolva["id"] == selected_id,
                    "trabada": tolva["id"] in jammed_ids,
                    "calibrando": running_here,
                    "calibracion_progreso": progress,
                }
            )
        return snapshot


def seleccionar_tolva(offset):
    global _tolva_seleccionada_idx
    with _tolvas_lock:
        _tolva_seleccionada_idx = (_tolva_seleccionada_idx + offset) % len(_tolvas)
    if gui_actualizar_funcion:
        try:
            gui_actualizar_funcion()
        except Exception as exc:
            print(f"[ERROR] GUI actualizar al cambiar tolva falló: {exc}")


def seleccionar_tolva_siguiente():
    seleccionar_tolva(1)


def seleccionar_tolva_anterior():
    seleccionar_tolva(-1)


def _seleccionar_siguiente_tolva_disponible():
    """
    Si la tolva seleccionada está trabada, intenta mover la selección
    a la siguiente tolva no trabada (circular).
    Debe llamarse con _tolvas_lock ya tomado.
    """
    global _tolva_seleccionada_idx
    if not _tolvas:
        return False

    total = len(_tolvas)
    start_idx = _tolva_seleccionada_idx

    for step in range(1, total + 1):
        idx = (start_idx + step) % total
        tolva_id = _tolvas[idx]["id"]
        if tolva_id not in _tolvas_trabadas:
            if idx != _tolva_seleccionada_idx:
                _tolva_seleccionada_idx = idx
                return True
            return False
    return False

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
    global bloqueo_emergencia, _ultima_tolva_motor_idx, _ultimo_apagado_motor_ts

    with _tolvas_lock:
        tolvas_local = [dict(t) for t in _tolvas]

    estado_anterior_sensor = {t["id"]: GPIO.input(t["sensor_pin"]) for t in tolvas_local}
    ficha_en_sensor = {t["id"]: False for t in tolvas_local}
    tiempo_inicio_pulso = {t["id"]: 0.0 for t in tolvas_local}
    tiempo_inicio_motor = 0.0
    motor_con_timeout_activo = False
    motor_tolva_idx = None

    print("[CORE] Iniciando hilo de control de motor multi-tolva con protección anti-quemado")
    destrabe_intentos = {}  # tolva_id -> intentos durante una corrida
    destrabe_ultimo_ts = {}  # tolva_id -> último intento

    while True:
        try:
            shared_buffer.process_gui_commands()
            should_abort_calibration = False
            should_finalize_calibration_no_pending = False
            with _tolvas_lock:
                if _auto_calibration.get("running"):
                    started = float(_auto_calibration.get("start_ts", 0.0) or 0.0)
                    max_duration = float(_auto_calibration.get("max_duration_s", 45.0) or 45.0)
                    if started > 0 and (time.time() - started) > max_duration:
                        should_abort_calibration = True
                    else:
                        target_samples = int(_auto_calibration.get("target_samples", 0) or 0)
                        counted_samples = int(_auto_calibration.get("counted_samples", 0) or 0)
                        if (
                            target_samples > 0
                            and counted_samples >= target_samples
                            and shared_buffer.get_fichas_restantes() <= 0
                            and not shared_buffer.get_motor_activo()
                        ):
                            # Evita quedar colgado esperando un pulso final de cierre.
                            should_finalize_calibration_no_pending = True

            if should_abort_calibration:
                _finalizar_auto_calibracion(success=False, error_msg="Timeout de auto-calibración (sin muestras suficientes).")
            elif should_finalize_calibration_no_pending:
                _finalizar_auto_calibracion(success=True)

            with _tolvas_lock:
                tolvas_local = [dict(t) for t in _tolvas]
                selected_idx = _tolva_seleccionada_idx
                selected_tolva = tolvas_local[selected_idx]
            _, _, timeout_motor_tolva = _calibracion_tolva(selected_tolva)
            cfg_runtime = cargar_configuracion()
            destrabe_cfg = _get_destrabe_cfg(selected_tolva, cfg_runtime)

            # --- Destrabe manual solicitado desde GUI ---
            req = None
            with _destrabe_request_lock:
                if _destrabe_requested.get("ts", 0) > 0:
                    req = dict(_destrabe_requested)
                    _destrabe_requested.update({"tolva_id": None, "ts": 0.0})
            if req and destrabe_cfg["enabled"] and destrabe_cfg["retroceso_s"] > 0:
                tolva_id_req = req.get("tolva_id")
                if tolva_id_req is None:
                    tolva_id_req = selected_tolva["id"]
                tolva_target = next((t for t in tolvas_local if t.get("id") == tolva_id_req), None) or selected_tolva
                _motor_off_all(tolvas_local)
                shared_buffer.set_motor_activo(False)
                motor_con_timeout_activo = False
                motor_tolva_idx = None
                _hacer_retroceso_en_hilo(tolva_target, destrabe_cfg["retroceso_s"])

            # Control del motor basado en fichas_restantes
            if shared_buffer.get_fichas_restantes() > 0 and not bloqueo_emergencia:
                if (not shared_buffer.get_motor_activo()) or (motor_tolva_idx != selected_idx):
                    # Apagar todos los motores para evitar doble activación accidental
                    _motor_off_all(tolvas_local)
                    _motor_set(selected_tolva, "fwd")
                    shared_buffer.set_motor_activo(True)
                    motor_tolva_idx = selected_idx
                    _ultima_tolva_motor_idx = selected_idx
                    tiempo_inicio_motor = time.time()
                    motor_con_timeout_activo = True
                    destrabe_intentos[selected_tolva["id"]] = 0
                    with _tolvas_lock:
                        if _auto_calibration.get("running") and _auto_calibration.get("target_tolva_id") == selected_tolva["id"]:
                            _auto_calibration["motor_on_ts"] = time.time()
                    print(
                        f"[MOTOR ON] {selected_tolva['nombre']} | "
                        f"Fichas pendientes: {shared_buffer.get_fichas_restantes()}"
                    )

                elif motor_con_timeout_activo:
                    tiempo_motor_activo = time.time() - tiempo_inicio_motor
                    if tiempo_motor_activo > timeout_motor_tolva:
                        tolva_id = selected_tolva["id"]
                        now = time.time()
                        prev_ts = float(destrabe_ultimo_ts.get(tolva_id, 0.0) or 0.0)
                        intentos = int(destrabe_intentos.get(tolva_id, 0) or 0)
                        can_try = (
                            destrabe_cfg["enabled"]
                            and destrabe_cfg["auto_on_timeout"]
                            and destrabe_cfg["retroceso_s"] > 0
                            and selected_tolva.get("motor_pin_rev")
                            and intentos < destrabe_cfg["max_intentos"]
                            and (now - prev_ts) >= destrabe_cfg["cooldown_s"]
                        )
                        if can_try:
                            destrabe_intentos[tolva_id] = intentos + 1
                            destrabe_ultimo_ts[tolva_id] = now
                            print(
                                f"[DESTRABE] Timeout {tiempo_motor_activo:.2f}s en {selected_tolva['nombre']} → "
                                f"retroceso {destrabe_cfg['retroceso_s']:.2f}s (intento {intentos+1}/{destrabe_cfg['max_intentos']})"
                            )
                            _motor_off_all(tolvas_local)
                            shared_buffer.set_motor_activo(False)
                            motor_con_timeout_activo = False
                            motor_tolva_idx = None
                            _hacer_retroceso_en_hilo(selected_tolva, destrabe_cfg["retroceso_s"])
                            time.sleep(0.05)
                            continue

                        _motor_set(selected_tolva, "off")
                        shared_buffer.set_motor_activo(False)
                        motor_con_timeout_activo = False
                        calibrating_here = False
                        with _tolvas_lock:
                            calibrating_here = bool(
                                _auto_calibration.get("running")
                                and _auto_calibration.get("target_tolva_id") == selected_tolva["id"]
                            )

                        if calibrating_here:
                            # En calibración no hacemos fallback ni marcamos traba global.
                            # Abortamos calibración y dejamos el sistema estable.
                            shared_buffer.set_fichas_restantes(0)
                            _finalizar_auto_calibracion(
                                success=False,
                                error_msg=(
                                    f"Timeout durante auto-calibración en {selected_tolva['nombre']} "
                                    f"({tiempo_motor_activo:.1f}s > {timeout_motor_tolva}s)."
                                ),
                            )
                            print(
                                "[AUTO-CALIBRACIÓN] Abortada por timeout de motor "
                                f"en {selected_tolva['nombre']}."
                            )
                        else:
                            bloqueo_emergencia = True

                            with _tolvas_lock:
                                _tolvas_trabadas.add(selected_tolva["id"])
                                cambio_automatico = _seleccionar_siguiente_tolva_disponible()

                            fichas_pendientes = shared_buffer.get_fichas_restantes()
                            print("=" * 60)
                            print("⚠️  [EMERGENCIA - MOTOR TRABADO] ⚠️")
                            print("=" * 60)
                            print(f"Tolva: {selected_tolva['nombre']}")
                            print(f"Tiempo transcurrido: {tiempo_motor_activo:.1f}s (límite: {timeout_motor_tolva}s)")
                            print(f"Fichas pendientes de dispensar: {fichas_pendientes}")
                            if cambio_automatico:
                                with _tolvas_lock:
                                    nueva = _tolvas[_tolva_seleccionada_idx]["nombre"]
                                print(f"[CORE] Cambio automático a {nueva} por traba de tolva.")
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
                    _motor_off_all(tolvas_local)
                    shared_buffer.set_motor_activo(False)
                    _ultima_tolva_motor_idx = motor_tolva_idx
                    _ultimo_apagado_motor_ts = time.time()
                    motor_tolva_idx = None
                    motor_con_timeout_activo = False
                    print("[MOTOR OFF] Todas las fichas expendidas")
                    threading.Thread(target=enviar_datos_venta_servidor, daemon=True).start()

            # Leer sensores de todas las tolvas
            tiempo_actual = time.time()
            for idx, tolva in enumerate(tolvas_local):
                tolva_id = tolva["id"]
                sensor_pin = tolva["sensor_pin"]
                pulso_min_tolva, pulso_max_tolva, _ = _calibracion_tolva(tolva)
                estado_actual_sensor = GPIO.input(sensor_pin)

                if not ficha_en_sensor[tolva_id]:
                    if estado_anterior_sensor[tolva_id] == GPIO.HIGH and estado_actual_sensor == GPIO.LOW:
                        ficha_en_sensor[tolva_id] = True
                        tiempo_inicio_pulso[tolva_id] = tiempo_actual
                        with _tolvas_lock:
                            if _auto_calibration.get("running") and _auto_calibration.get("target_tolva_id") == tolva_id:
                                motor_on_ts = _auto_calibration.get("motor_on_ts")
                                if motor_on_ts:
                                    _auto_calibration["first_pulse_delays"].append(max(0.0, tiempo_actual - float(motor_on_ts)))
                                _auto_calibration["pulse_open_ts"] = tiempo_actual

                        # Si estaba trabada, al primer pulso la consideramos destrabada
                        with _tolvas_lock:
                            if tolva_id in _tolvas_trabadas:
                                _tolvas_trabadas.remove(tolva_id)
                                print(f"[CORE] {tolva['nombre']} destrabada por pulso de sensor.")
                                if gui_actualizar_funcion:
                                    try:
                                        gui_actualizar_funcion()
                                    except Exception as e:
                                        print(f"[ERROR] GUI actualizar falló: {e}")

                        # Contamos ficha si proviene de la tolva activa.
                        # Los pulsos tardíos (motor ya apagado) NO se cuentan:
                        # se usan solo para auto-calibrar la ventana del sensor.
                        counted = False
                        calibrated_late_pulse = False
                        if motor_tolva_idx == idx and shared_buffer.get_fichas_restantes() > 0:
                            shared_buffer.decrementar_fichas_restantes()
                            tiempo_inicio_motor = time.time()
                            counted = True
                        else:
                            with _tolvas_lock:
                                ventana_tardia = float(_ventana_pulso_tardio_por_tolva.get(idx, 0.3))
                            delay_off = time.time() - float(_ultimo_apagado_motor_ts or 0.0)
                            if (
                                shared_buffer.get_fichas_restantes() <= 0
                                and _ultima_tolva_motor_idx == idx
                                and delay_off >= 0.0
                                and delay_off <= ventana_tardia
                            ):
                                _actualizar_auto_calibracion_tardia(idx, delay_off)
                                calibrated_late_pulse = True

                        if counted or calibrated_late_pulse:
                            if calibrated_late_pulse:
                                print(
                                    f"[AUTO-CALIBRACIÓN] Pulso tardío detectado en {tolva['nombre']} "
                                    f"(delay={delay_off:.3f}s, no contado)."
                                )
                            if counted:
                                print(
                                    f"✅ [FICHA DETECTADA - {tolva['nombre']}] "
                                    f"Restantes: {shared_buffer.get_fichas_restantes()}"
                                )

                                # Corte por evento: al detectar la ficha objetivo (restantes = 0),
                                # apagamos motor inmediatamente sin esperar otro ciclo del loop.
                                if (
                                    shared_buffer.get_fichas_restantes() <= 0
                                    and shared_buffer.get_motor_activo()
                                    and motor_tolva_idx == idx
                                ):
                                    for tolva_off in tolvas_local:
                                        _motor_set(tolva_off, "off")
                                    shared_buffer.set_motor_activo(False)
                                    _ultima_tolva_motor_idx = idx
                                    _ultimo_apagado_motor_ts = time.time()
                                    motor_tolva_idx = None
                                    motor_con_timeout_activo = False
                                    print(f"[MOTOR OFF EVENTO] Objetivo alcanzado en {tolva['nombre']}")
                                    threading.Thread(target=enviar_datos_venta_servidor, daemon=True).start()

                            if counted:
                                try:
                                    actualizar_registro("ficha", 1)
                                except Exception as e:
                                    print(f"[ERROR] actualizar_registro falló (motor continúa): {e}")

                            if gui_actualizar_funcion and counted:
                                try:
                                    gui_actualizar_funcion()
                                except Exception as e:
                                    print(f"[ERROR] GUI actualizar falló: {e}")
                            if counted:
                                with _tolvas_lock:
                                    if _auto_calibration.get("running") and _auto_calibration.get("target_tolva_id") == tolva_id:
                                        _auto_calibration["counted_samples"] = int(_auto_calibration.get("counted_samples", 0)) + 1
                                        _auto_calibration["total_counted_samples"] = int(_auto_calibration.get("total_counted_samples", 0)) + 1
                                        _auto_calibration["motor_on_ts"] = time.time()
                else:
                    if estado_actual_sensor == GPIO.HIGH:
                        duracion_pulso = tiempo_actual - tiempo_inicio_pulso[tolva_id]
                        ficha_en_sensor[tolva_id] = False
                        should_finalize_calibration = False
                        with _tolvas_lock:
                            if _auto_calibration.get("running") and _auto_calibration.get("target_tolva_id") == tolva_id:
                                pulse_open_ts = _auto_calibration.get("pulse_open_ts")
                                if pulse_open_ts:
                                    _auto_calibration["pulse_durations"].append(max(0.001, tiempo_actual - float(pulse_open_ts)))
                                _auto_calibration["pulse_open_ts"] = None
                                target_samples = int(_auto_calibration.get("target_samples", 0))
                                counted_samples = int(_auto_calibration.get("counted_samples", 0))
                                measured_samples = len(_auto_calibration.get("pulse_durations", []))
                                if target_samples > 0 and counted_samples >= target_samples and measured_samples >= target_samples:
                                    should_finalize_calibration = True

                        if should_finalize_calibration:
                            _finalizar_auto_calibracion(success=True)

                        if duracion_pulso < pulso_min_tolva:
                            print(
                                f"[RUIDO POSIBLE] {tolva['nombre']} pulso muy corto: "
                                f"{duracion_pulso*1000:.1f}ms"
                            )
                        elif duracion_pulso > pulso_max_tolva:
                            print(
                                f"[ADVERTENCIA] {tolva['nombre']} pulso muy largo: "
                                f"{duracion_pulso*1000:.1f}ms"
                            )

                estado_anterior_sensor[tolva_id] = estado_actual_sensor

            time.sleep(0.005)

        except Exception as e:
            # El loop del motor NUNCA debe morir. Cualquier excepción se loga y se continúa.
            print(f"[MOTOR LOOP ERROR - CONTINUANDO] {type(e).__name__}: {e}")
            try:
                _motor_off_all(tolvas_local)
                shared_buffer.set_motor_activo(False)
            except Exception:
                pass
            time.sleep(0.1)

# --- PROGRAMA PRINCIPAL ---
def iniciar_sistema():
    """Inicializa el sistema de control de motor (sin GUI)"""
    _cargar_tolvas_desde_config()
    _setup_gpio_tolvas()
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
    with _tolvas_lock:
        for tolva in _tolvas:
            _motor_set(tolva, "off")
    GPIO.cleanup()
    print("Sistema detenido")


class CoreController:
    """
    Fachada OO del módulo core para inyección en GUI/main.
    Mantiene compatibilidad con la lógica actual basada en funciones.
    """

    @property
    def sensor_pin(self):
        with _tolvas_lock:
            return _tolvas[_tolva_seleccionada_idx]["sensor_pin"]

    def get_tolvas_status(self):
        return get_tolvas_status()

    def seleccionar_tolva_siguiente(self):
        seleccionar_tolva_siguiente()

    def seleccionar_tolva_anterior(self):
        seleccionar_tolva_anterior()

    def recargar_tolvas_desde_config(self):
        recargar_tolvas_desde_config()

    def iniciar_auto_calibracion_tolva(self, tolva_id, samples=32):
        return iniciar_auto_calibracion_tolva(tolva_id, samples=samples)

    def obtener_estado_auto_calibracion(self):
        return get_auto_calibration_status()

    def register_gui_update(self, callback):
        registrar_gui_actualizar(callback)

    def register_gui_motor_alert(self, callback):
        registrar_gui_alerta_motor(callback)

    def unlock_motor(self):
        desbloquear_motor()

    def request_unjam(self, tolva_id=None):
        solicitar_destrabe(tolva_id=tolva_id)

    def start(self):
        return iniciar_sistema()

    def stop(self):
        detener_sistema()