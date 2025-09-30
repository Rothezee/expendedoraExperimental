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
        cls._pins[pin] = cls.LOW
        print(f"Pin {pin} configurado como {mode}")

    @classmethod
    def output(cls, pin, state):
        cls._pins[pin] = state
        print(f"Pin {pin} cambiado a {'HIGH' if state else 'LOW'}")

    @classmethod
    def input(cls, pin):
        return cls._pins.get(pin, cls.LOW)

    @classmethod
    def cleanup(cls):
        cls._pins.clear()
        print("GPIO limpiado")
