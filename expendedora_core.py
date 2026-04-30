try:
    import RPi.GPIO as GPIO  # type: ignore[import-not-found]

    GPIO.setwarnings(False)
except ImportError:
    from infra.gpio_pc_stub import GPIO

import time
import threading
import json
import os
from collections import deque
from datetime import datetime
import shared_buffer
from infra.config_repository import ConfigRepository
from infra.telemetry_client import TelemetryClient

# PERSISTENCIA EN EJECUCION: este archivo se relee/guarda durante runtime.
# Si queres que los pines queden permanentes, modifica config.json.
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
        "motor_pin": 2,
        "sensor_pin": 4,
        "calibracion": {"pulso_min_s": 0.05, "pulso_max_s": 0.5, "timeout_motor_s": 2.0},
    },
    {
        "id": 2,
        "nombre": "Tolva 2",
        "motor_pin": 2,
        "sensor_pin": 4,
        "calibracion": {"pulso_min_s": 0.05, "pulso_max_s": 0.5, "timeout_motor_s": 2.0},
    },
    {
        "id": 3,
        "nombre": "Tolva 3",
        "motor_pin": 2,
        "sensor_pin": 4,
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

_motor_io_lock = threading.Lock()
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
_ultima_tolva_motor_idx = None
_tolva_motor_activa_idx = None
_ultimo_apagado_motor_ts = 0.0
_ventana_pulso_tardio_por_tolva = {}
_sensor_interrupts_cfg = {"bouncetime_ms": DEFAULT_SENSOR_BOUNCETIME_MS}
_sensor_event_lock = threading.Lock()
_sensor_event_queue = deque()
_sensor_pin_to_tolvas = {}
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
    global _tolvas, _ventana_pulso_tardio_por_tolva, _sensor_interrupts_cfg
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
        # Dejar motores apagados al inicializar.
        GPIO.output(tolva["motor_pin"], GPIO.HIGH if tolva.get("motor_active_low", DEFAULT_MOTOR_ACTIVE_LOW) else GPIO.LOW)
        motor_rev = tolva.get("motor_pin_rev")
        if motor_rev:
            GPIO.setup(int(motor_rev), GPIO.OUT)
            GPIO.output(int(motor_rev), GPIO.HIGH if tolva.get("motor_active_low", DEFAULT_MOTOR_ACTIVE_LOW) else GPIO.LOW)


def _sensor_bouncetime_ms(tolva):
    try:
        value = int(float(tolva.get("sensor_bouncetime_ms", _sensor_interrupts_cfg.get("bouncetime_ms", DEFAULT_SENSOR_BOUNCETIME_MS))))
    except (TypeError, ValueError):
        value = int(_sensor_interrupts_cfg.get("bouncetime_ms", DEFAULT_SENSOR_BOUNCETIME_MS))
    return max(0, min(1000, value))


def _clear_sensor_events():
    with _sensor_event_lock:
        _sensor_event_queue.clear()


def _pop_sensor_events():
    with _sensor_event_lock:
        events = list(_sensor_event_queue)
        _sensor_event_queue.clear()
    return events


def _sensor_edge_callback(channel):
    pin = int(channel)
    tolva_ids = list(_sensor_pin_to_tolvas.get(pin, []))
    if not tolva_ids:
        return

    # Si varias tolvas comparten el mismo sensor BCM, asociamos el evento
    # a la tolva activa/seleccionada para que el conteo real coincida con la
    # simulación y con la operación vigente.
    tolva_id = None
    if len(tolva_ids) == 1:
        tolva_id = int(tolva_ids[0])
    else:
        selected_tolva_id = None
        running_tolva_id = None
        last_motor_tolva_id = None
        with _tolvas_lock:
            if 0 <= _tolva_seleccionada_idx < len(_tolvas):
                selected_tolva_id = int(_tolvas[_tolva_seleccionada_idx]["id"])
            if _tolva_motor_activa_idx is not None and 0 <= _tolva_motor_activa_idx < len(_tolvas):
                running_tolva_id = int(_tolvas[_tolva_motor_activa_idx]["id"])
            if _ultima_tolva_motor_idx is not None and 0 <= _ultima_tolva_motor_idx < len(_tolvas):
                last_motor_tolva_id = int(_tolvas[_ultima_tolva_motor_idx]["id"])

        if shared_buffer.get_motor_activo() and running_tolva_id in tolva_ids:
            tolva_id = running_tolva_id
        elif shared_buffer.get_motor_activo() and last_motor_tolva_id in tolva_ids:
            tolva_id = last_motor_tolva_id
        elif selected_tolva_id in tolva_ids:
            tolva_id = selected_tolva_id
        elif last_motor_tolva_id in tolva_ids:
            tolva_id = last_motor_tolva_id
        else:
            tolva_id = int(tolva_ids[0])

    if tolva_id is None:
        return
    try:
        state = GPIO.input(channel)
    except Exception:
        return
    with _sensor_event_lock:
        _sensor_event_queue.append(
            {
                "tolva_id": int(tolva_id),
                "pin": int(channel),
                "state": state,
                "ts": time.time(),
            }
        )


def inject_sensor_pulse_events(pin=None):
    """
    Simula una interrupción del sensor (secuencia equivalente HIGH→LOW→HIGH)
    encolando el mismo formato que _sensor_edge_callback.

    Si varias tolvas comparten BCM (ej. todas en pin 4), el callback IRQ solo puede
    asociar una tolva al pin; acá siempre usa la tolva SELECCIONADA en GUI, coherente
    con expedición y prueba.

    Usa la misma cola que IRQ; mismo GPIO que importa este módulo (RPi o stub PC).
    """
    with _tolvas_lock:
        t = dict(_tolvas[_tolva_seleccionada_idx])
    pin_i = int(t["sensor_pin"] if pin is None else pin)
    tolva_id = int(t["id"])
    t_base = time.time()
    sequence = [(0.0, GPIO.HIGH), (0.025, GPIO.LOW), (0.085, GPIO.HIGH)]
    with _sensor_event_lock:
        for dt, state in sequence:
            _sensor_event_queue.append(
                {
                    "tolva_id": tolva_id,
                    "pin": pin_i,
                    "state": state,
                    "ts": t_base + dt,
                }
            )
    print(
        f"[SIM CORE] BCM {pin_i}: pulsos sintéticos → tolva {tolva_id} ({t.get('nombre', '')})"
    )


def _remove_sensor_interrupts():
    pins = list(_sensor_pin_to_tolvas.keys())
    for pin in pins:
        try:
            GPIO.remove_event_detect(int(pin))
        except Exception:
            pass
    _sensor_pin_to_tolvas.clear()
    _clear_sensor_events()


def _setup_sensor_interrupts():
    _remove_sensor_interrupts()
    if not hasattr(GPIO, "add_event_detect"):
        print("[CORE] GPIO backend sin interrupciones; se mantiene modo compatibilidad.")
        return
    with _tolvas_lock:
        tolvas_snapshot = [dict(t) for t in _tolvas]
    for tolva in tolvas_snapshot:
        pin = int(tolva["sensor_pin"])
        bouncetime_ms = _sensor_bouncetime_ms(tolva)
        bucket = _sensor_pin_to_tolvas.setdefault(pin, [])
        tolva_id = int(tolva["id"])
        if tolva_id not in bucket:
            bucket.append(tolva_id)
        try:
            GPIO.add_event_detect(
                pin,
                GPIO.BOTH,
                callback=_sensor_edge_callback,
                bouncetime=bouncetime_ms,
            )
        except Exception as exc:
            print(f"[CORE] No se pudo registrar interrupción sensor pin {pin}: {exc}")
    print(
        "[CORE] Interrupciones sensor activas en pines: "
        + ", ".join(str(p) for p in sorted(_sensor_pin_to_tolvas.keys()))
    )
    shared_pins = [pin for pin, ids in _sensor_pin_to_tolvas.items() if len(ids) > 1]
    if shared_pins:
        details = ", ".join(f"BCM {pin}: tolvas {ids}" for pin, ids in _sensor_pin_to_tolvas.items() if len(ids) > 1)
        print(f"[CORE] Aviso: sensores compartidos detectados ({details}).")


def _motor_levels(tolva):
    active_low = bool(tolva.get("motor_active_low", DEFAULT_MOTOR_ACTIVE_LOW))
    return (GPIO.LOW, GPIO.HIGH) if active_low else (GPIO.HIGH, GPIO.LOW)  # (on, off)


def _motor_set(tolva, mode):
    """
    mode: 'off' | 'fwd' | 'rev'
    Con 2 relés: motor_pin = adelante, motor_pin_rev = reversa.
    """
    fwd = int(tolva["motor_pin"])
    rev = tolva.get("motor_pin_rev")
    rev = int(rev) if rev else None
    on_level, off_level = _motor_levels(tolva)
    with _motor_io_lock:
        if mode == "off":
            GPIO.output(fwd, off_level)
            if rev:
                GPIO.output(rev, off_level)
            return
        if mode == "fwd":
            # Break-before-make: apaga ambos primero para evitar solape.
            GPIO.output(fwd, off_level)
            if rev:
                GPIO.output(rev, off_level)
            time.sleep(0.02)
            if rev:
                GPIO.output(rev, off_level)
            GPIO.output(fwd, on_level)
            return
        if mode == "rev":
            if not rev:
                GPIO.output(fwd, off_level)
                return
            # Break-before-make: apaga ambos primero para evitar solape.
            GPIO.output(fwd, off_level)
            GPIO.output(rev, off_level)
            time.sleep(0.02)
            GPIO.output(fwd, off_level)
            GPIO.output(rev, on_level)
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


def _hacer_retroceso_bloqueante(tolva, dur_s):
    """
    Retroceso bloqueante (se ejecuta en el hilo del control de motor).
    Esto evita que el loop vuelva a prender 'adelante' y pise la reversa
    después de pocos milisegundos.
    """
    nombre = tolva.get("nombre", "Tolva")
    try:
        dur = float(dur_s)
    except (TypeError, ValueError):
        dur = 0.0
    dur = max(0.0, min(10.0, dur))
    print(f"[DESTRABE] Retroceso {dur:.2f}s en {nombre}")
    _motor_set(tolva, "rev")
    if dur > 0:
        time.sleep(dur)
    _motor_set(tolva, "off")
    print(f"[DESTRABE] Fin retroceso en {nombre}")


def recargar_tolvas_desde_config():
    """Recarga configuración de tolvas/calibración en caliente."""
    _cargar_tolvas_desde_config()
    _setup_gpio_tolvas()
    _setup_sensor_interrupts()


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
    global bloqueo_emergencia, _ultima_tolva_motor_idx, _tolva_motor_activa_idx, _ultimo_apagado_motor_ts

    with _tolvas_lock:
        tolvas_local = [dict(t) for t in _tolvas]

    estado_anterior_sensor = {t["id"]: GPIO.input(t["sensor_pin"]) for t in tolvas_local}
    ficha_en_sensor = {t["id"]: False for t in tolvas_local}
    tiempo_inicio_pulso = {t["id"]: 0.0 for t in tolvas_local}
    ultima_transicion_poll_ts = {t["id"]: 0.0 for t in tolvas_local}
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
                _tolva_motor_activa_idx = None
                _hacer_retroceso_bloqueante(tolva_target, destrabe_cfg["retroceso_s"])

            # Control del motor basado en fichas_restantes
            if shared_buffer.get_fichas_restantes() > 0 and not bloqueo_emergencia:
                if (not shared_buffer.get_motor_activo()) or (motor_tolva_idx != selected_idx):
                    # Apagar todos los motores para evitar doble activación accidental
                    _motor_off_all(tolvas_local)
                    _motor_set(selected_tolva, "fwd")
                    shared_buffer.set_motor_activo(True)
                    motor_tolva_idx = selected_idx
                    _ultima_tolva_motor_idx = selected_idx
                    _tolva_motor_activa_idx = selected_idx
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
                            _tolva_motor_activa_idx = None
                            _hacer_retroceso_bloqueante(selected_tolva, destrabe_cfg["retroceso_s"])
                            # Al terminar el retroceso, el loop reintentará prender adelante
                            # si aún hay fichas pendientes.
                            continue

                        _motor_set(selected_tolva, "off")
                        shared_buffer.set_motor_activo(False)
                        motor_con_timeout_activo = False
                        _tolva_motor_activa_idx = None
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
                    _tolva_motor_activa_idx = None
                    motor_con_timeout_activo = False
                    print("[MOTOR OFF] Todas las fichas expendidas")
                    threading.Thread(target=enviar_datos_venta_servidor, daemon=True).start()

            # Sincronizar estado local por si cambiaron IDs/sensores por recarga de config.
            tolva_idx_by_id = {}
            for idx, tolva in enumerate(tolvas_local):
                tolva_id = int(tolva["id"])
                tolva_idx_by_id[tolva_id] = idx
                if tolva_id not in estado_anterior_sensor:
                    estado_anterior_sensor[tolva_id] = GPIO.input(tolva["sensor_pin"])
                    ficha_en_sensor[tolva_id] = False
                    tiempo_inicio_pulso[tolva_id] = 0.0
            for stale_id in list(estado_anterior_sensor.keys()):
                if stale_id not in tolva_idx_by_id:
                    estado_anterior_sensor.pop(stale_id, None)
                    ficha_en_sensor.pop(stale_id, None)
                    tiempo_inicio_pulso.pop(stale_id, None)
                    ultima_transicion_poll_ts.pop(stale_id, None)
                elif stale_id not in ultima_transicion_poll_ts:
                    ultima_transicion_poll_ts[stale_id] = 0.0

            # Procesar eventos de interrupción del sensor.
            sensor_events = _pop_sensor_events()
            # Fallback robusto: si IRQ falla/intermitente en Raspberry, detectamos
            # transiciones por lectura directa y las encolamos con debounce.
            for idx, tolva in enumerate(tolvas_local):
                tolva_id = int(tolva["id"])
                try:
                    estado_actual = GPIO.input(tolva["sensor_pin"])
                except Exception:
                    continue
                estado_prev = estado_anterior_sensor.get(tolva_id, estado_actual)
                if estado_actual == estado_prev:
                    continue
                # Evitar duplicados cuando también llega evento por interrupción.
                duplicated = False
                for ev in sensor_events:
                    if int(ev.get("tolva_id", 0) or 0) != tolva_id:
                        continue
                    if ev.get("state") == estado_actual:
                        duplicated = True
                        break
                if duplicated:
                    continue
                now_ts = time.time()
                min_dt = max(0.001, _sensor_bouncetime_ms(tolva) / 1000.0)
                if (now_ts - float(ultima_transicion_poll_ts.get(tolva_id, 0.0))) < min_dt:
                    continue
                ultima_transicion_poll_ts[tolva_id] = now_ts
                sensor_events.append(
                    {
                        "tolva_id": tolva_id,
                        "pin": int(tolva["sensor_pin"]),
                        "state": estado_actual,
                        "ts": now_ts,
                        "source": "poll",
                    }
                )
            for event in sensor_events:
                tolva_id = int(event.get("tolva_id", 0) or 0)
                idx = tolva_idx_by_id.get(tolva_id)
                if idx is None:
                    continue
                tolva = tolvas_local[idx]
                pulso_min_tolva, pulso_max_tolva, _ = _calibracion_tolva(tolva)
                estado_actual_sensor = event.get("state")
                estado_prev = estado_anterior_sensor.get(tolva_id, GPIO.HIGH)
                tiempo_actual = float(event.get("ts") or time.time())

                # Ignorar duplicados sin transición real.
                if estado_actual_sensor == estado_prev:
                    continue

                if not ficha_en_sensor[tolva_id]:
                    # Conteo principal: flanco de bajada.
                    if estado_prev == GPIO.HIGH and estado_actual_sensor == GPIO.LOW:
                        ficha_en_sensor[tolva_id] = True
                        tiempo_inicio_pulso[tolva_id] = tiempo_actual
                        with _tolvas_lock:
                            if _auto_calibration.get("running") and _auto_calibration.get("target_tolva_id") == tolva_id:
                                motor_on_ts = _auto_calibration.get("motor_on_ts")
                                if motor_on_ts:
                                    _auto_calibration["first_pulse_delays"].append(max(0.0, tiempo_actual - float(motor_on_ts)))
                                _auto_calibration["pulse_open_ts"] = tiempo_actual

                        # Si estaba trabada, al primer pulso la consideramos destrabada.
                        with _tolvas_lock:
                            if tolva_id in _tolvas_trabadas:
                                _tolvas_trabadas.remove(tolva_id)
                                print(f"[CORE] {tolva['nombre']} destrabada por pulso de sensor.")
                                if gui_actualizar_funcion:
                                    try:
                                        gui_actualizar_funcion()
                                    except Exception as e:
                                        print(f"[ERROR] GUI actualizar falló: {e}")

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
                                # Corte por evento.
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
                                    _tolva_motor_activa_idx = None
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
                    # Flanco de subida: cerrar pulso y medir duración (diagnóstico/calibración).
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

            time.sleep(0.002)

        except Exception as e:
            # El loop del motor NUNCA debe morir. Cualquier excepción se loga y se continúa.
            print(f"[MOTOR LOOP ERROR - CONTINUANDO] {type(e).__name__}: {e}")
            try:
                _motor_off_all(tolvas_local)
                shared_buffer.set_motor_activo(False)
                _tolva_motor_activa_idx = None
            except Exception:
                pass
            time.sleep(0.1)

# --- PROGRAMA PRINCIPAL ---
def iniciar_sistema():
    """Inicializa el sistema de control de motor (sin GUI)"""
    _cargar_tolvas_desde_config()
    _setup_gpio_tolvas()
    _setup_sensor_interrupts()
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
    _remove_sensor_interrupts()
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

    def simulate_sensor_pulse(self, pin=None):
        """Puente desde la GUI para probar dispatch sin segundo módulo GPIO."""
        inject_sensor_pulse_events(pin=pin)

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