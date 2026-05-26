#pragma once

/* Arduino Uno — cableado tolva 1
 *   Pin 13 = motor adelante (D13, LED integrado comparte pin; apagado con relé active-LOW = HIGH)
 *   Pin 11 = motor atrás / reversa
 *   Pin  9 = sensor óptico (INPUT_PULLUP)
 * Relés típicos active-LOW: HIGH en pin = relé apagado. */
#define TEST_STANDALONE 0
#define TEST_FICHAS_INICIALES 5

#define DEFAULT_MOTOR_PIN 13
#define DEFAULT_MOTOR_REV_PIN 11
#define DEFAULT_SENSOR_PIN 9
#define DEFAULT_MOTOR_ACTIVE_LOW 1

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

#define DEBUG_SENSOR 1
#define DEBUG_SENSOR_INTERVAL_MS 400

#ifndef max
#define max(a, b) ((a) > (b) ? (a) : (b))
#endif
