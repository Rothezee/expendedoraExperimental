#pragma once

/* Arduino Uno — cableado tolva 1 (debe coincidir con config.json → maquina.hoppers[])
 *   Pin 10 = motor adelante
 *   Pin 12 = motor atrás / reversa
 *   Pin  9 = sensor óptico
 * Relés típicos active-LOW: HIGH en pin = relé apagado.
 * Sensor: `sensor_blocked_high=false` reposo HIGH (INPUT_PULLUP), corte LOW.
 *          `sensor_blocked_high=true`  reposo LOW, corte HIGH (INPUT). */

#define TEST_STANDALONE 0
#define TEST_FICHAS_INICIALES 5

#define DEFAULT_MOTOR_PIN 10
#define DEFAULT_MOTOR_REV_PIN 12
#define DEFAULT_SENSOR_PIN 9
#define DEFAULT_MOTOR_ACTIVE_LOW 1
#define DEFAULT_SENSOR_BLOCKED_HIGH 1

#if TEST_STANDALONE
#define TEST_LED_PIN 13
#define TEST_LED_ACTIVE_HIGH 0
#define TEST_BOOT_BLINK 1
#endif

#define DEFAULT_SENSOR_BOUNCE_MS 8
#define DEFAULT_PULSO_MIN_S 0.05f
#define DEFAULT_PULSO_MAX_S 0.5f
#if TEST_STANDALONE
#define DEFAULT_TIMEOUT_MOTOR_S 30.0f
#else
#define DEFAULT_TIMEOUT_MOTOR_S 2.0f
#endif
#define MAX_HOPPERS 3

/* Depuración sensor: 1 = logs en monitor serial (cerrar main.py antes). */
#define DEBUG_SENSOR 1
#define DEBUG_SENSOR_INTERVAL_MS 40
#ifndef max
#define max(a, b) ((a) > (b) ? (a) : (b))
#endif
