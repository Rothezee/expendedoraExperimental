#!/usr/bin/env python3
"""
Test de detección de pulso completo (HIGH->LOW->HIGH)
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

print("=" * 70)
print("TEST DE DETECCIÓN DE PULSO COMPLETO")
print("=" * 70)

# Inicializar
print("\n[1] Inicializando sistema...")
core.iniciar_sistema()
time.sleep(0.5)

# Estado inicial
print(f"\n[2] Estado inicial:")
print(f"    Fichas restantes: {core.obtener_fichas_restantes()}")
print(f"    Motor: {core.motor_activo}")

# Agregar 5 fichas
print(f"\n[3] Agregando 5 fichas...")
core.agregar_fichas(5)
time.sleep(0.3)
print(f"    Fichas pendientes: {core.obtener_fichas_restantes()}")
print(f"    Motor encendido: {core.motor_activo}")

# Simular fichas con pulsos completos
print(f"\n[4] Simulando 5 fichas con pulsos completos...")

for i in range(5):
    print(f"\n  === Ficha {i+1} ===")

    # Simular pulso completo: HIGH -> LOW (ficha bloquea) -> HIGH (ficha pasa)
    print(f"    Generando pulso completo...")
    GPIO._pins[core.ENTHOPER] = GPIO.HIGH
    time.sleep(0.02)  # Sensor en HIGH

    GPIO._pins[core.ENTHOPER] = GPIO.LOW  # Ficha bloquea sensor
    time.sleep(0.08)  # Ficha bloqueando (80ms)

    GPIO._pins[core.ENTHOPER] = GPIO.HIGH  # Ficha pasó
    time.sleep(0.15)  # Esperar procesamiento

    # Verificar
    restantes = core.obtener_fichas_restantes()
    expendidas = core.obtener_fichas_expendidas()
    print(f"    -> Restantes: {restantes} | Expendidas: {expendidas}")

# Verificación final
time.sleep(0.3)
print(f"\n[5] Resultado Final:")
print(f"    Fichas restantes: {core.obtener_fichas_restantes()}")
print(f"    Fichas expendidas: {core.obtener_fichas_expendidas()}")
print(f"    Motor activo: {core.motor_activo}")

# Verificar resultado
esperado = 5
real = core.obtener_fichas_expendidas()

print("\n" + "=" * 70)
if real == esperado and core.obtener_fichas_restantes() == 0 and not core.motor_activo:
    print(f"✓ PRUEBA EXITOSA: {real}/{esperado} fichas expendidas correctamente")
    print(f"✓ Motor apagado correctamente")
else:
    print(f"✗ PRUEBA FALLIDA")
    print(f"  Esperado: {esperado} fichas")
    print(f"  Real: {real} fichas")
    print(f"  Restantes: {core.obtener_fichas_restantes()}")
print("=" * 70)

core.detener_sistema()
