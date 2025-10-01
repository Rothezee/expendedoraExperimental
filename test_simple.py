#!/usr/bin/env python3
"""
Prueba simple del sistema de control de motor
"""

# Configurar para no necesitar requests
import sys
sys.path.insert(0, '/tmp/cc-agent/57802247/project')

# Mock de requests para evitar la dependencia
class MockRequests:
    class Response:
        status_code = 200
        text = "OK"

    @staticmethod
    def post(*args, **kwargs):
        return MockRequests.Response()

    class RequestException(Exception):
        pass

sys.modules['requests'] = MockRequests()

import expendedora_core as core
import time
from gpio_sim import GPIO

print("=" * 60)
print("PRUEBA SIMPLE DEL SISTEMA DE MOTOR")
print("=" * 60)

# Inicializar
print("\n[1] Inicializando sistema...")
core.iniciar_sistema()
time.sleep(0.5)

print(f"\nEstado inicial:")
print(f"  Fichas restantes: {core.obtener_fichas_restantes()}")
print(f"  Fichas expendidas: {core.obtener_fichas_expendidas()}")
print(f"  Motor activo: {core.motor_activo}")

# Agregar 3 fichas
print(f"\n[2] Agregando 3 fichas...")
total = core.agregar_fichas(3)
time.sleep(0.3)

print(f"\nDespués de agregar:")
print(f"  Fichas restantes: {core.obtener_fichas_restantes()}")
print(f"  Total devuelto: {total}")
print(f"  Motor activo: {core.motor_activo}")

# Simular 3 fichas saliendo
print(f"\n[3] Simulando 3 fichas saliendo...")
for i in range(3):
    print(f"\n  Ficha {i+1}:")
    GPIO.simulate_sensor_pulse(core.ENTHOPER)
    time.sleep(0.3)
    print(f"    Restantes: {core.obtener_fichas_restantes()}")
    print(f"    Expendidas: {core.obtener_fichas_expendidas()}")
    print(f"    Motor: {'ON' if core.motor_activo else 'OFF'}")

print(f"\n[4] Estado final:")
print(f"  Fichas restantes: {core.obtener_fichas_restantes()}")
print(f"  Fichas expendidas: {core.obtener_fichas_expendidas()}")
print(f"  Motor activo: {core.motor_activo}")

# Verificación
print("\n" + "=" * 60)
if core.obtener_fichas_restantes() == 0 and core.obtener_fichas_expendidas() == 3 and not core.motor_activo:
    print("✓ PRUEBA EXITOSA: El sistema funciona correctamente")
else:
    print("✗ PRUEBA FALLIDA: Valores incorrectos")
print("=" * 60)

core.detener_sistema()
