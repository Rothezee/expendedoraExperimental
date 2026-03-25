"""
Estado compartido entre GUI y Core.
Encapsula datos y lock en una clase para reducir acoplamiento global.
"""

from queue import Queue
import threading
import json
import os

STATE_FILE = "buffer_state.json"
PERSISTED_KEYS = (
    "fichas_restantes",
    "fichas_expendidas",
    "fichas_expendidas_sesion",
    "cuenta",
    "r_cuenta",
)
_persist_lock = threading.Lock()
_persist_timer = None


class MachineState:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
            "fichas_restantes": 0,
            "fichas_expendidas": 0,
            "fichas_expendidas_sesion": 0,
            "cuenta": 0,
            "r_cuenta": 0,
            "promo1_count": 0,
            "promo2_count": 0,
            "promo3_count": 0,
            "motor_activo": False,
        }
        self._load_persisted_state()

    def get(self, key):
        with self._lock:
            return self._data[key]

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def add(self, key, value):
        with self._lock:
            self._data[key] += value
            return self._data[key]

    def reset_session(self):
        with self._lock:
            self._data["fichas_expendidas_sesion"] = 0
            self._data["r_cuenta"] = 0
            total = self._data["fichas_expendidas"]
        print(f"[BUFFER] Contador de sesión y r_cuenta reiniciados. Total global: {total}")

    def decrementar_fichas_restantes(self):
        with self._lock:
            if self._data["fichas_restantes"] > 0:
                self._data["fichas_restantes"] -= 1
                self._data["fichas_expendidas"] += 1
                self._data["fichas_expendidas_sesion"] += 1
                return True
        return False

    def snapshot(self):
        with self._lock:
            return dict(self._data)

    def _load_persisted_state(self):
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as file_obj:
                loaded = json.load(file_obj)
            if not isinstance(loaded, dict):
                return
            for key in PERSISTED_KEYS:
                if key in loaded:
                    self._data[key] = loaded[key]
        except Exception as exc:
            print(f"[BUFFER] No se pudo cargar estado persistido: {exc}")


gui_to_core_queue = Queue()
_state = MachineState()
gui_update_callback = None


def _flush_state():
    global _persist_timer
    try:
        snap = _state.snapshot()
        persisted = {key: snap.get(key, 0) for key in PERSISTED_KEYS}
        with open(STATE_FILE, "w", encoding="utf-8") as file_obj:
            json.dump(persisted, file_obj, indent=2)
    except Exception as exc:
        print(f"[BUFFER] Error guardando estado persistido: {exc}")
    finally:
        with _persist_lock:
            _persist_timer = None


def _schedule_state_persist():
    global _persist_timer
    with _persist_lock:
        if _persist_timer is not None:
            _persist_timer.cancel()
        _persist_timer = threading.Timer(0.4, _flush_state)
        _persist_timer.daemon = True
        _persist_timer.start()


def set_gui_update_callback(callback):
    global gui_update_callback
    gui_update_callback = callback


def get_fichas_restantes():
    return _state.get("fichas_restantes")


def get_fichas_expendidas():
    return _state.get("fichas_expendidas_sesion")


def get_fichas_expendidas_total():
    return _state.get("fichas_expendidas")


def set_fichas_restantes(value):
    _state.set("fichas_restantes", value)
    _schedule_state_persist()


def set_fichas_expendidas(value):
    _state.set("fichas_expendidas", value)
    _schedule_state_persist()


def reset_fichas_expendidas_sesion():
    _state.reset_session()
    _schedule_state_persist()


def agregar_fichas(cantidad):
    new_value = _state.add("fichas_restantes", cantidad)
    _schedule_state_persist()
    return new_value


def decrementar_fichas_restantes():
    ok = _state.decrementar_fichas_restantes()
    if ok:
        _schedule_state_persist()
    return ok


def get_motor_activo():
    return _state.get("motor_activo")


def set_motor_activo(value):
    _state.set("motor_activo", value)


def get_cuenta():
    return _state.get("cuenta")


def set_cuenta(value):
    _state.set("cuenta", value)
    _schedule_state_persist()


def add_to_cuenta(value):
    _state.add("cuenta", value)
    _schedule_state_persist()


def get_r_cuenta():
    return _state.get("r_cuenta")


def set_r_cuenta(value):
    _state.set("r_cuenta", value)
    _schedule_state_persist()


def increment_promo_count(promo_num):
    _state.add(f"promo{promo_num}_count", 1)


def process_gui_commands():
    comando_procesado = False
    while not gui_to_core_queue.empty():
        command = gui_to_core_queue.get()
        comando_procesado = True
        if command["type"] == "add_fichas":
            cantidad = command["cantidad"]
            agregar_fichas(cantidad)
            print(f"[CORE] ✓ Fichas agregadas: {cantidad} | Total: {get_fichas_restantes()}")
        elif command["type"] == "promo":
            promo_num = command["promo_num"]
            fichas = command["fichas"]
            agregar_fichas(fichas)
            increment_promo_count(promo_num)
            print(f"[CORE] ✓ Promo {promo_num} activada: {fichas} fichas | Total: {get_fichas_restantes()}")
        elif command["type"] == "reset_sesion":
            reset_fichas_expendidas_sesion()

    if comando_procesado and gui_update_callback:
        try:
            gui_update_callback()
        except Exception as e:
            print(f"[ERROR] Callback GUI falló: {e}")
