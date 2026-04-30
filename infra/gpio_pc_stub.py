"""
Stub ligero de RPi.GPIO para desarrollo en PC (ImportError de RPi.GPIO).
En Raspberry Pi debe usarse el módulo real; no exponer este archivo en producción
salvo accidentalmente por import fallback.
"""


class GPIO:
    BCM = "BCM"
    IN = "IN"
    OUT = "OUT"
    PUD_UP = "PULL_UP"
    BOTH = "BOTH"
    HIGH = 1
    LOW = 0

    _pins = {}
    _event_callbacks = {}

    @classmethod
    def setmode(cls, mode):
        print(f"GPIO modo configurado (PC stub): {mode}")

    @classmethod
    def setup(cls, pin, mode, pull_up_down=None):
        if pull_up_down == cls.PUD_UP:
            cls._pins[pin] = cls.HIGH
        else:
            cls._pins[pin] = cls.LOW
        print(f"Pin {pin} configurado como {mode} (PC stub)")

    @classmethod
    def output(cls, pin, state):
        cls._pins[pin] = state
        print(f"Pin {pin} cambiado a {'HIGH' if state else 'LOW'} (PC stub)")

    @classmethod
    def input(cls, pin):
        return cls._pins.get(pin, cls.HIGH)

    @classmethod
    def cleanup(cls):
        for pin in list(cls._event_callbacks.keys()):
            cls.remove_event_detect(pin)
        cls._pins.clear()
        print("GPIO limpiado (PC stub)")

    @classmethod
    def add_event_detect(cls, pin, edge, callback=None, bouncetime=0):
        cls._event_callbacks[int(pin)] = {"callback": callback, "edge": edge, "bouncetime": bouncetime}

    @classmethod
    def remove_event_detect(cls, pin):
        cls._event_callbacks.pop(int(pin), None)

    @classmethod
    def _emit_event(cls, pin):
        data = cls._event_callbacks.get(int(pin), {})
        cb = data.get("callback")
        if cb:
            try:
                cb(int(pin))
            except Exception:
                pass

    @classmethod
    def simulate_sensor_pulse(cls, pin):
        """Opcional: pruebas manuales; la GUI usa inject_sensor_pulse_events en el core."""
        import time

        print(f"[SIMULACIÓN PC STUB] Sensor {pin}: Generando pulso...")
        cls._pins[pin] = cls.HIGH
        cls._emit_event(pin)
        time.sleep(0.02)
        cls._pins[pin] = cls.LOW
        cls._emit_event(pin)
        time.sleep(0.05)
        cls._pins[pin] = cls.HIGH
        cls._emit_event(pin)
        print(f"[SIMULACIÓN PC STUB] Sensor {pin}: Pulso completado")
