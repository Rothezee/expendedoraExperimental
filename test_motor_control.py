#!/usr/bin/env python3
"""
Script de prueba para verificar el control del motor basado en fichas_restantes
"""

import expendedora_core as core
import time
from gpio_sim import GPIO

def test_motor_control():
    print("=" * 60)
    print("TEST DE CONTROL DE MOTOR")
    print("=" * 60)

    # Inicializar el sistema
    print("\n[1] Inicializando sistema...")
    core.iniciar_sistema()
    time.sleep(1)

    # Verificar estado inicial
    print(f"\n[2] Estado inicial:")
    print(f"    Fichas restantes: {core.obtener_fichas_restantes()}")
    print(f"    Fichas expendidas: {core.obtener_fichas_expendidas()}")
    print(f"    Motor activo: {core.motor_activo}")

    # Agregar fichas
    print(f"\n[3] Agregando 5 fichas...")
    core.agregar_fichas(5)
    time.sleep(0.5)

    print(f"    Fichas restantes: {core.obtener_fichas_restantes()}")
    print(f"    Motor activo: {core.motor_activo}")
    print(f"    Estado del pin del motor: {GPIO.input(core.MOTOR_PIN)}")

    # Simular salida de fichas
    print(f"\n[4] Simulando salida de fichas (3 fichas)...")
    for i in range(3):
        print(f"    Simulando ficha {i+1}...")
        GPIO.simulate_sensor_pulse(core.ENTHOPER)
        time.sleep(0.2)
        print(f"    -> Fichas restantes: {core.obtener_fichas_restantes()}")
        print(f"    -> Fichas expendidas: {core.obtener_fichas_expendidas()}")
        print(f"    -> Motor activo: {core.motor_activo}")

    # Agregar más fichas
    print(f"\n[5] Agregando 3 fichas más...")
    core.agregar_fichas(3)
    time.sleep(0.5)

    print(f"    Fichas restantes: {core.obtener_fichas_restantes()}")
    print(f"    Motor activo: {core.motor_activo}")

    # Simular salida de todas las fichas
    print(f"\n[6] Simulando salida de todas las fichas restantes...")
    fichas_a_expender = core.obtener_fichas_restantes()
    for i in range(fichas_a_expender):
        print(f"    Simulando ficha {i+1}/{fichas_a_expender}...")
        GPIO.simulate_sensor_pulse(core.ENTHOPER)
        time.sleep(0.2)
        print(f"    -> Fichas restantes: {core.obtener_fichas_restantes()}")
        print(f"    -> Motor activo: {core.motor_activo}")

    # Verificar estado final
    print(f"\n[7] Estado final:")
    print(f"    Fichas restantes: {core.obtener_fichas_restantes()}")
    print(f"    Fichas expendidas: {core.obtener_fichas_expendidas()}")
    print(f"    Motor activo: {core.motor_activo}")
    print(f"    Estado del pin del motor: {GPIO.input(core.MOTOR_PIN)}")

    # Detener el sistema
    print(f"\n[8] Deteniendo sistema...")
    core.detener_sistema()

    print("\n" + "=" * 60)
    print("TEST COMPLETADO")
    print("=" * 60)

if __name__ == "__main__":
    test_motor_control()
