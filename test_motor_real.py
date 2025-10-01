#!/usr/bin/env python3
"""
Test del motor simulando comportamiento real con velocidad del motor
"""

import sys
sys.path.insert(0, '/tmp/cc-agent/57802247/project')

# Mock de requests
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
print("TEST REAL DEL MOTOR CON VELOCIDAD SIMULADA")
print("=" * 60)

# Inicializar
print("\n[INICIO] Inicializando sistema...")
core.iniciar_sistema()
time.sleep(0.5)

print(f"\nEstado inicial:")
print(f"  Fichas restantes: {core.obtener_fichas_restantes()}")
print(f"  Motor activo: {core.motor_activo}")

# Agregar 10 fichas
print(f"\n[TEST] Agregando 10 fichas...")
total = core.agregar_fichas(10)
time.sleep(0.5)

print(f"\nMotor encendido: {core.motor_activo}")
print(f"Fichas pendientes: {total}")

# Simular fichas saliendo con delay realista (una ficha cada 0.4-0.5 segundos)
print(f"\n[TEST] Simulando fichas saliendo (velocidad realista)...")
for i in range(10):
    print(f"\n  Ficha #{i+1}:")

    # Simular pulso del sensor
    GPIO.simulate_sensor_pulse(core.ENTHOPER)

    # Esperar un poco para que el sistema procese
    time.sleep(0.15)

    # Mostrar estado
    restantes = core.obtener_fichas_restantes()
    expendidas = core.obtener_fichas_expendidas()
    motor = "ON" if core.motor_activo else "OFF"

    print(f"    Restantes: {restantes} | Expendidas: {expendidas} | Motor: {motor}")

    # Delay entre fichas (simula velocidad del motor)
    time.sleep(0.35)

# Verificación final
time.sleep(0.5)
print(f"\n[RESULTADO FINAL]")
print(f"  Fichas restantes: {core.obtener_fichas_restantes()}")
print(f"  Fichas expendidas: {core.obtener_fichas_expendidas()}")
print(f"  Motor activo: {core.motor_activo}")

# Verificar
esperado_restantes = 0
esperado_expendidas = 10
real_restantes = core.obtener_fichas_restantes()
real_expendidas = core.obtener_fichas_expendidas()

print("\n" + "=" * 60)
if real_restantes == esperado_restantes and real_expendidas == esperado_expendidas and not core.motor_activo:
    print("✓ PRUEBA EXITOSA")
    print(f"  ✓ Restantes: {real_restantes}/{esperado_restantes}")
    print(f"  ✓ Expendidas: {real_expendidas}/{esperado_expendidas}")
    print(f"  ✓ Motor apagado correctamente")
else:
    print("✗ PRUEBA FALLIDA")
    print(f"  Esperado - Restantes: {esperado_restantes}, Expendidas: {esperado_expendidas}")
    print(f"  Real     - Restantes: {real_restantes}, Expendidas: {real_expendidas}")
print("=" * 60)

core.detener_sistema()
