"""

Estado compartido entre GUI y Core.

Encapsula datos y lock en una clase para reducir acoplamiento global.

"""



from queue import Queue

import threading



from infra.state_store import (

    BUFFER_PERSISTED_KEYS,

    default_buffer,

    save_buffer_only,

)



STATE_FILE = "buffer_state.json"  # legacy; lectura solo en recover_state

PERSISTED_KEYS = BUFFER_PERSISTED_KEYS

_persist_lock = threading.Lock()

_persist_timer = None
_persist_retry_count = 0

_dispense_arm_pending = False

_dispense_arm_lock = threading.Lock()

_last_gui_contadores: dict | None = None

_last_gui_contadores_apertura: dict | None = None

_last_gui_contadores_parciales: dict | None = None





class MachineState:

    def __init__(self):

        self._lock = threading.Lock()

        self._data = {

            "fichas_restantes": 0,

            "fichas_expendidas": 0,

            "fichas_expendidas_sesion": 0,

            "cuenta": 0,

            "r_cuenta": 0,

            "motor_activo": False,
            "motor_direccion": "detenido",

        }



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



    def hydrate_from_buffer_dict(self, buffer: dict):

        with self._lock:

            for key in BUFFER_PERSISTED_KEYS:

                if key in buffer:

                    self._data[key] = buffer[key]





gui_to_core_queue = Queue()

_state = MachineState()

gui_update_callback = None





def register_gui_counters(

    contadores: dict,

    contadores_apertura: dict | None = None,

    contadores_parciales: dict | None = None,

) -> None:

    """Registra últimos contadores GUI para persistencia completa en eventos críticos."""

    global _last_gui_contadores, _last_gui_contadores_apertura, _last_gui_contadores_parciales

    _last_gui_contadores = dict(contadores) if contadores else None

    _last_gui_contadores_apertura = dict(contadores_apertura) if contadores_apertura else None

    _last_gui_contadores_parciales = dict(contadores_parciales) if contadores_parciales else None





def _buffer_payload() -> dict:

    snap = _state.snapshot()

    return {key: snap.get(key, 0) for key in BUFFER_PERSISTED_KEYS}





def _schedule_state_persist(delay_s: float = 0.4):

    global _persist_timer

    with _persist_lock:

        if _persist_timer is not None:

            _persist_timer.cancel()

        _persist_timer = threading.Timer(max(0.05, float(delay_s)), lambda: persist_now("debounced"))

        _persist_timer.daemon = True

        _persist_timer.start()





def flush_pending():

    """Cancela debounce pendiente y persiste de inmediato."""

    global _persist_timer

    with _persist_lock:

        if _persist_timer is not None:

            _persist_timer.cancel()

            _persist_timer = None

    persist_now("flush_pending")





def persist_now(reason: str = "", *, immediate: bool = True) -> None:

    """Persiste buffer; si hay contadores GUI registrados, snapshot completo."""

    if not immediate:

        _schedule_state_persist()

        return

    from infra.state_store import build_snapshot, load_snapshot, save_snapshot

    global _persist_retry_count



    buf = _buffer_payload()

    try:
        if _last_gui_contadores is not None:
            existing = load_snapshot() or build_snapshot(reason=reason)
            snap = build_snapshot(
                buffer=buf,
                contadores=_last_gui_contadores,
                contadores_apertura=_last_gui_contadores_apertura or existing.get("contadores_apertura"),
                contadores_parciales=_last_gui_contadores_parciales or existing.get("contadores_parciales"),
                reason=reason,
            )
            save_snapshot(snap)
        else:
            save_buffer_only(buf, reason=reason)
        _persist_retry_count = 0
    except (PermissionError, OSError) as exc:
        _persist_retry_count = min(_persist_retry_count + 1, 6)
        retry_delay = min(5.0, 0.4 * (2 ** (_persist_retry_count - 1)))
        print(
            f"[BUFFER WARN] Persistencia diferida ({reason or 'sin_motivo'}): {exc}. "
            f"Reintento en {retry_delay:.1f}s"
        )
        _schedule_state_persist(retry_delay)





def hydrate_from_recovery(buffer: dict) -> None:

    _state.hydrate_from_buffer_dict(buffer or default_buffer())





def set_gui_update_callback(callback):

    global gui_update_callback

    gui_update_callback = callback





def get_fichas_restantes():

    return _state.get("fichas_restantes")





def get_fichas_expendidas():

    return _state.get("fichas_expendidas_sesion")





def get_fichas_expendidas_total():

    return _state.get("fichas_expendidas")





def set_fichas_restantes(value, *, immediate: bool = True):

    _state.set("fichas_restantes", value)

    if immediate:

        persist_now("set_fichas_restantes")

    else:

        _schedule_state_persist()





def set_fichas_expendidas(value, *, immediate: bool = True):

    _state.set("fichas_expendidas", value)

    if immediate:

        persist_now("set_fichas_expendidas")

    else:

        _schedule_state_persist()





def reset_fichas_expendidas_sesion(*, immediate: bool = True):

    _state.reset_session()

    if immediate:

        persist_now("reset_sesion")

    else:

        _schedule_state_persist()





def consume_dispense_arm_pending() -> bool:
    global _dispense_arm_pending
    with _dispense_arm_lock:
        pending = _dispense_arm_pending
        _dispense_arm_pending = False
        return pending


def _mark_dispense_arm_pending() -> None:
    global _dispense_arm_pending
    with _dispense_arm_lock:
        _dispense_arm_pending = True


def agregar_fichas(cantidad, *, immediate: bool = True):

    new_value = _state.add("fichas_restantes", cantidad)

    if immediate:

        persist_now("add_fichas")

    else:

        _schedule_state_persist()

    return new_value





def decrementar_fichas_restantes(*, immediate: bool = True):

    ok = _state.decrementar_fichas_restantes()

    if ok:

        if immediate:

            persist_now("token")

        else:

            _schedule_state_persist()

    return ok





def get_motor_activo():

    return _state.get("motor_activo")





def set_motor_activo(value):

    _state.set("motor_activo", value)


def get_motor_direccion():

    return _state.get("motor_direccion")


def set_motor_direccion(value):

    value_norm = str(value or "detenido").strip().lower()
    if value_norm not in {"adelante", "atras", "detenido"}:
        value_norm = "detenido"
    _state.set("motor_direccion", value_norm)





def get_cuenta():

    return _state.get("cuenta")





def set_cuenta(value, *, immediate: bool = True):

    _state.set("cuenta", value)

    if immediate:

        persist_now("set_cuenta")

    else:

        _schedule_state_persist()





def add_to_cuenta(value, *, immediate: bool = True):

    _state.add("cuenta", value)

    if immediate:

        persist_now("add_cuenta")

    else:

        _schedule_state_persist()





def get_r_cuenta():

    return _state.get("r_cuenta")





def set_r_cuenta(value, *, immediate: bool = True):

    _state.set("r_cuenta", value)

    if immediate:

        persist_now("set_r_cuenta")

    else:

        _schedule_state_persist()





def process_gui_commands():

    comando_procesado = False

    while not gui_to_core_queue.empty():

        command = gui_to_core_queue.get()

        comando_procesado = True

        if command["type"] == "add_fichas":

            cantidad = command["cantidad"]

            agregar_fichas(cantidad)

            _mark_dispense_arm_pending()

            print(f"[CORE] ✓ Fichas agregadas: {cantidad} | Total: {get_fichas_restantes()}")

        elif command["type"] == "promo":

            promo_num = command["promo_num"]

            fichas = command["fichas"]

            agregar_fichas(fichas)

            _mark_dispense_arm_pending()

            print(f"[CORE] ✓ Promo {promo_num} activada: {fichas} fichas | Total: {get_fichas_restantes()}")

        elif command["type"] == "reset_sesion":

            reset_fichas_expendidas_sesion()



    if comando_procesado and gui_update_callback:

        try:

            gui_update_callback()

        except Exception as e:

            print(f"[ERROR] Callback GUI falló: {e}")


