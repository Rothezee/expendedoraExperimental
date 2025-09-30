# gpio_sim.py - Simulación de RPi.GPIO para pruebas en PC

class GPIO:
    BCM = "BCM"
    IN = "IN"
    OUT = "OUT"
    PUD_UP = "PULL_UP"
    HIGH = 1
    LOW = 0

    _pins = {}

    @classmethod
    def setmode(cls, mode):
        print(f"GPIO modo configurado: {mode}")

    @classmethod
    def setup(cls, pin, mode, pull_up_down=None):
        # Inicializar en HIGH si tiene pull-up
        if pull_up_down == cls.PUD_UP:
            cls._pins[pin] = cls.HIGH
        else:
            cls._pins[pin] = cls.LOW
        print(f"Pin {pin} configurado como {mode}")

    @classmethod
    def output(cls, pin, state):
        cls._pins[pin] = state
        print(f"Pin {pin} cambiado a {'HIGH' if state else 'LOW'}")

    @classmethod
    def input(cls, pin):
        return cls._pins.get(pin, cls.HIGH)  # Sensores con pull-up por defecto en HIGH

    @classmethod
    def cleanup(cls):
        cls._pins.clear()
        print("GPIO limpiado")

    @classmethod
    def simulate_sensor_pulse(cls, pin):
        """Simula un pulso del sensor (HIGH -> LOW -> HIGH)"""
        import time
        print(f"[SIMULACIÓN] Sensor {pin}: Generando pulso...")
        cls._pins[pin] = cls.HIGH
        time.sleep(0.02)
        cls._pins[pin] = cls.LOW
        time.sleep(0.05)
        cls._pins[pin] = cls.HIGH
        print(f"[SIMULACIÓN] Sensor {pin}: Pulso completado")
