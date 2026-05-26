/*
 * esp32_dispenser.ino — Expendedora (motor + sensor óptico)
 * Placa: Arduino Uno (USB nativo, 115200 baud, JSON por línea).
 * Protocolo PC: infra/esp32_protocol.py
 *
 * Arduino IDE: Placa "Arduino Uno", librería ArduinoJson v7.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <stdarg.h>
#include <string.h>
#include "config.h"

typedef struct {
  int id;
  int motorPin;
  int motorRevPin;
  int sensorPin;
  bool motorActiveLow;
  int sensorBounceMs;
  float pulsoMinS;
  float pulsoMaxS;
  float timeoutMotorS;
} HopperConfig;

typedef struct {
  bool enabled;
  bool autoOnTimeout;
  float retrocesoS;
  int maxIntentos;
  float cooldownS;
} DestrabeConfig;

static HopperConfig hoppers[MAX_HOPPERS];
static int activeHopperIdx = 0;
static DestrabeConfig destrabeCfg;
static int targetRemaining = 0;
static bool motorOn = false;
static unsigned long motorOnSinceMs = 0;
static unsigned long motorArmedAtMs = 0;
static const unsigned long MOTOR_SENSOR_GRACE_MS = 600;
static const unsigned long MIN_TOKEN_GAP_MS = 280;
static int destrabeAttempts = 0;
static unsigned long lastDestrabeMs = 0;
static bool jammed = false;
static bool configReady = false;
static bool debugMotorSensor = false;
static unsigned long lastSensorDbgMs = 0;

static bool sensorPulseActive = false;
static unsigned long pulseStartMs = 0;
static unsigned long lastCountMs = 0;
static int lastSensorState = HIGH;

static char rxLine[513];
static size_t rxLen = 0;

static void initHopperDefaults(HopperConfig *h, int id) {
  h->id = id;
  h->motorPin = DEFAULT_MOTOR_PIN;
  h->motorRevPin = DEFAULT_MOTOR_REV_PIN;
  h->sensorPin = DEFAULT_SENSOR_PIN;
  h->motorActiveLow = (DEFAULT_MOTOR_ACTIVE_LOW != 0);
  h->sensorBounceMs = DEFAULT_SENSOR_BOUNCE_MS;
  h->pulsoMinS = DEFAULT_PULSO_MIN_S;
  h->pulsoMaxS = DEFAULT_PULSO_MAX_S;
  h->timeoutMotorS = DEFAULT_TIMEOUT_MOTOR_S;
}

static HopperConfig *activeHopper(void) {
  return &hoppers[activeHopperIdx];
}

static void dbg(const char *cat, const char *msg) {
  if (!debugMotorSensor) return;
  Serial.print("[DBG ");
  Serial.print(cat);
  Serial.print("] ");
  Serial.println(msg);
}

static void dbgFmt(const char *cat, const char *fmt, ...) {
  if (!debugMotorSensor) return;
  char buf[96];
  va_list args;
  va_start(args, fmt);
  vsnprintf(buf, sizeof(buf), fmt, args);
  va_end(args);
  dbg(cat, buf);
}

static bool sensorDebugOn(void) {
  return (DEBUG_SENSOR != 0) || debugMotorSensor;
}

static void dbgSensor(const char *msg) {
  if (!sensorDebugOn()) return;
  Serial.print("[DBG SENSOR] ");
  Serial.println(msg);
}

static void dbgSensorFmt(const char *fmt, ...) {
  if (!sensorDebugOn()) return;
  char buf[128];
  va_list args;
  va_start(args, fmt);
  vsnprintf(buf, sizeof(buf), fmt, args);
  va_end(args);
  dbgSensor(buf);
}

static int motorOnLevel(const HopperConfig *h) {
  return h->motorActiveLow ? LOW : HIGH;
}

static int motorOffLevel(const HopperConfig *h) {
  return h->motorActiveLow ? HIGH : LOW;
}

static void emitEvent(const char *type) {
  StaticJsonDocument<192> doc;
  doc["dir"] = "evt";
  doc["type"] = type;
  doc["hopper_id"] = activeHopper()->id;
  doc["remaining"] = targetRemaining;
  serializeJson(doc, Serial);
  Serial.println();
}

static void emitEventMsg(const char *type, const char *msg) {
  StaticJsonDocument<192> doc;
  doc["dir"] = "evt";
  doc["type"] = type;
  doc["hopper_id"] = activeHopper()->id;
  doc["remaining"] = targetRemaining;
  doc["message"] = msg;
  serializeJson(doc, Serial);
  Serial.println();
}

static void motorForward(const HopperConfig *h) {
  if (h->motorRevPin >= 0) digitalWrite(h->motorRevPin, motorOffLevel(h));
  digitalWrite(h->motorPin, motorOnLevel(h));
}

static void motorReverse(const HopperConfig *h) {
  digitalWrite(h->motorPin, motorOffLevel(h));
  if (h->motorRevPin >= 0) digitalWrite(h->motorRevPin, motorOnLevel(h));
}

static void motorOffPins(const HopperConfig *h) {
  digitalWrite(h->motorPin, motorOffLevel(h));
  if (h->motorRevPin >= 0) digitalWrite(h->motorRevPin, motorOffLevel(h));
}

#if TEST_STANDALONE
static void testLedWrite(bool on) {
  pinMode(TEST_LED_PIN, OUTPUT);
  int level = on ? (TEST_LED_ACTIVE_HIGH ? HIGH : LOW) : (TEST_LED_ACTIVE_HIGH ? LOW : HIGH);
  digitalWrite(TEST_LED_PIN, level);
  if (sensorDebugOn()) {
    dbgSensorFmt("LED GPIO%d -> %s (write=%d read=%d)", TEST_LED_PIN, on ? "ON" : "OFF", level,
                 digitalRead(TEST_LED_PIN));
  }
}

static void testBootBlink(void) {
#if TEST_BOOT_BLINK
  pinMode(TEST_LED_PIN, OUTPUT);
  for (int i = 0; i < 5; i++) {
    testLedWrite(true);
    delay(200);
    testLedWrite(false);
    delay(200);
  }
  if (sensorDebugOn()) {
    dbgSensorFmt("BOOT blink listo en GPIO%d (ACTIVE_HIGH=%d)", TEST_LED_PIN, TEST_LED_ACTIVE_HIGH);
  }
#endif
}
#endif

static void applyMotorOutput(const HopperConfig *h, bool on) {
#if TEST_STANDALONE
  (void)h;
  testLedWrite(on);
#else
  if (on) {
    motorForward(h);
  } else {
    motorOffPins(h);
  }
#endif
}

static void forceRelaysOffSafe(void) {
#if TEST_STANDALONE
  pinMode(TEST_LED_PIN, OUTPUT);
  digitalWrite(TEST_LED_PIN, TEST_LED_ACTIVE_HIGH ? LOW : HIGH);
#else
  pinMode(DEFAULT_MOTOR_PIN, OUTPUT);
  digitalWrite(DEFAULT_MOTOR_PIN, HIGH);
#if DEFAULT_MOTOR_REV_PIN >= 0
  pinMode(DEFAULT_MOTOR_REV_PIN, OUTPUT);
  digitalWrite(DEFAULT_MOTOR_REV_PIN, HIGH);
#endif
#endif
}

static void setMotorState(bool on) {
  HopperConfig *h = activeHopper();
  if (on && !configReady) {
    dbg("MOTOR", "setMotorState(ON) bloqueado: sin CONFIG");
    return;
  }
  if (on == motorOn) return;
  motorOn = on;
  if (on) {
    dbgFmt("MOTOR", "ON pin=%d rev=%d target=%d", h->motorPin, h->motorRevPin, targetRemaining);
    applyMotorOutput(h, true);
    motorOnSinceMs = millis();
    motorArmedAtMs = millis();
    emitEvent("MOTOR_ON");
  } else {
    dbgFmt("MOTOR", "OFF pin=%d target=%d", h->motorPin, targetRemaining);
    applyMotorOutput(h, false);
    emitEvent("MOTOR_OFF");
  }
}

static void applyHopperPins(const HopperConfig *h) {
#if !TEST_STANDALONE
  pinMode(h->motorPin, OUTPUT);
  digitalWrite(h->motorPin, motorOffLevel(h));
  delay(5);
  digitalWrite(h->motorPin, motorOffLevel(h));
  if (h->motorRevPin >= 0) {
    pinMode(h->motorRevPin, OUTPUT);
    digitalWrite(h->motorRevPin, motorOffLevel(h));
    delay(5);
    digitalWrite(h->motorRevPin, motorOffLevel(h));
  }
#endif
  pinMode(h->sensorPin, INPUT_PULLUP);
}

static void loadHopperFromJson(JsonObject hopper, int idx) {
  if (idx < 0 || idx >= MAX_HOPPERS) return;
  HopperConfig *h = &hoppers[idx];
  h->id = hopper["id"] | (idx + 1);
  h->motorPin = hopper["motor_pin"] | DEFAULT_MOTOR_PIN;
  if (!hopper["motor_pin_rev"].isNull()) {
    h->motorRevPin = hopper["motor_pin_rev"].as<int>();
  } else {
    h->motorRevPin = -1;
  }
  h->sensorPin = hopper["sensor_pin"] | DEFAULT_SENSOR_PIN;
  h->motorActiveLow = hopper["motor_active_low"] | true;
  h->sensorBounceMs = hopper["sensor_bouncetime_ms"] | DEFAULT_SENSOR_BOUNCE_MS;
  JsonObject cal = hopper["calibracion"];
  if (!cal.isNull()) {
    h->pulsoMinS = cal["pulso_min_s"] | DEFAULT_PULSO_MIN_S;
    h->pulsoMaxS = cal["pulso_max_s"] | DEFAULT_PULSO_MAX_S;
    h->timeoutMotorS = cal["timeout_motor_s"] | DEFAULT_TIMEOUT_MOTOR_S;
  } else {
    h->pulsoMinS = DEFAULT_PULSO_MIN_S;
    h->pulsoMaxS = DEFAULT_PULSO_MAX_S;
    h->timeoutMotorS = DEFAULT_TIMEOUT_MOTOR_S;
  }
  if (h->sensorBounceMs <= 0) h->sensorBounceMs = DEFAULT_SENSOR_BOUNCE_MS;
  applyHopperPins(h);
}

static void handleConfig(JsonDocument &doc) {
  if (doc["hopper"].is<JsonObject>()) {
    loadHopperFromJson(doc["hopper"].as<JsonObject>(), activeHopperIdx);
  }
  if (doc["hoppers"].is<JsonArray>()) {
    JsonArray arr = doc["hoppers"].as<JsonArray>();
    int i = 0;
    for (JsonObject obj : arr) {
      loadHopperFromJson(obj, i);
      i++;
      if (i >= MAX_HOPPERS) break;
    }
  }
  if (doc["destrabe"].is<JsonObject>()) {
    JsonObject d = doc["destrabe"];
    destrabeCfg.enabled = d["enabled"] | true;
    destrabeCfg.autoOnTimeout = d["auto_on_timeout"] | true;
    destrabeCfg.retrocesoS = d["retroceso_s"] | 1.5f;
    destrabeCfg.maxIntentos = d["max_intentos"] | 1;
    destrabeCfg.cooldownS = d["cooldown_s"] | 2.0f;
  }
  if (doc["debug"].is<bool>()) debugMotorSensor = doc["debug"].as<bool>();
  jammed = false;
  destrabeAttempts = 0;
#if TEST_STANDALONE
  armTestStandalone();
#else
  targetRemaining = 0;
  configReady = true;
  setMotorState(false);
#endif
  dbg("CONFIG", debugMotorSensor ? "READY debug=ON" : "READY debug=OFF");
  emitEvent("READY");
}

static void handleSetTarget(int remaining) {
  if (!configReady) {
    dbg("MOTOR", "SET_TARGET ignorado: sin CONFIG");
    return;
  }
  dbgFmt("MOTOR", "SET_TARGET %d -> %d", targetRemaining, max(0, remaining));
  targetRemaining = max(0, remaining);
  jammed = false;
  sensorPulseActive = false;
  lastSensorState = digitalRead(activeHopper()->sensorPin);
  lastCountMs = millis();
  if (targetRemaining > 0) {
    setMotorState(true);
  } else {
    setMotorState(false);
    emitEvent("RUN_DONE");
  }
  emitEvent("SYNC");
}

static void doUnjam(float retrocesoS) {
  HopperConfig *h = activeHopper();
  setMotorState(false);
  if (h->motorRevPin < 0) {
    emitEvent("UNJAM_DONE");
    return;
  }
  motorReverse(h);
  delay((unsigned long)(retrocesoS * 1000.0f));
  motorOffPins(h);
  jammed = false;
  emitEvent("UNJAM_DONE");
  if (targetRemaining > 0) setMotorState(true);
}

static void countToken(void) {
  if (targetRemaining <= 0) return;
  HopperConfig *h = activeHopper();
  unsigned long now = millis();
  unsigned long minGap = (unsigned long)(h->pulsoMinS * 1000.0f);
  if (minGap < MIN_TOKEN_GAP_MS) minGap = MIN_TOKEN_GAP_MS;
  if (h->sensorBounceMs > (int)minGap) minGap = (unsigned long)h->sensorBounceMs;
  if (lastCountMs > 0 && (now - lastCountMs) < minGap) {
    dbgSensorFmt("TOKEN rechazado gap=%lu ms (min=%lu)", (unsigned long)(now - lastCountMs), minGap);
    return;
  }
  targetRemaining--;
  dbgSensorFmt("TOKEN OK remaining=%d pulso_ms=%lu", targetRemaining,
                 pulseStartMs > 0 ? (unsigned long)(now - pulseStartMs) : 0UL);
  lastCountMs = millis();
  motorOnSinceMs = millis();
  jammed = false;
  emitEvent("TOKEN");
  if (targetRemaining <= 0) {
    setMotorState(false);
    emitEvent("RUN_DONE");
#if TEST_STANDALONE
    dbgSensor("TEST: lote terminado -> reinicio automatico");
    armTestStandalone();
#endif
  }
}

static void dbgSensorPeriodic(int rawState, unsigned long now) {
  if (!sensorDebugOn()) return;
  if (now - lastSensorDbgMs < (unsigned long)DEBUG_SENSOR_INTERVAL_MS) return;
  lastSensorDbgMs = now;
  HopperConfig *h = activeHopper();
  unsigned long graceLeft = 0;
  if (motorOn && targetRemaining > 0 && now >= motorArmedAtMs) {
    unsigned long elapsed = now - motorArmedAtMs;
    if (elapsed < MOTOR_SENSOR_GRACE_MS) graceLeft = MOTOR_SENSOR_GRACE_MS - elapsed;
  }
  unsigned long sinceToken = lastCountMs > 0 ? now - lastCountMs : 0;
  dbgSensorFmt(
      "pin=%d raw=%s(%d) motor=%d tgt=%d pulse=%d grace=%lums since_token=%lums bounce=%dms",
      h->sensorPin, rawState == LOW ? "LOW" : "HIGH", rawState, motorOn ? 1 : 0, targetRemaining,
      sensorPulseActive ? 1 : 0, graceLeft, sinceToken, h->sensorBounceMs);
}

static void processSensor(void) {
  HopperConfig *h = activeHopper();
  int state = digitalRead(h->sensorPin);
  unsigned long now = millis();
  dbgSensorPeriodic(state, now);
#if TEST_STANDALONE
  /* En prueba con botón no hace falta gracia del motor. */
#else
  if (motorOn && targetRemaining > 0 && (now - motorArmedAtMs) < MOTOR_SENSOR_GRACE_MS) {
    if (state != lastSensorState) {
      dbgSensorFmt("flanco %d->%d IGNORADO (gracia motor %lums)", lastSensorState, state,
                   (unsigned long)(MOTOR_SENSOR_GRACE_MS - (now - motorArmedAtMs)));
    }
    return;
  }
#endif
  if (state != lastSensorState) {
    dbgSensorFmt("flanco %d->%d motor=%d target=%d pulse_activo=%d", lastSensorState, state,
                 motorOn ? 1 : 0, targetRemaining, sensorPulseActive ? 1 : 0);
    if (lastSensorState == HIGH && state == LOW) {
      float minSep = (float)h->sensorBounceMs;
      if (minSep < 120.0f) minSep = 120.0f;
      float pulsoMs = h->pulsoMinS * 1000.0f;
      if (pulsoMs > minSep) minSep = pulsoMs;
      if (lastCountMs == 0 || (now - lastCountMs) >= (unsigned long)minSep) {
        sensorPulseActive = true;
        pulseStartMs = now;
        dbgSensorFmt("pulso INICIO (min_sep=%dms)", (int)minSep);
      } else {
        dbgSensorFmt("LOW ignorado: muy pronto tras ultimo token (%lums < %dms)",
                     (unsigned long)(now - lastCountMs), (int)minSep);
      }
    } else if (sensorPulseActive && state == HIGH) {
      unsigned long pulsoDur = now - pulseStartMs;
      sensorPulseActive = false;
#if TEST_STANDALONE
      if (targetRemaining > 0) {
        dbgSensorFmt("pulso FIN dur=%lums -> contar TOKEN (test)", pulsoDur);
        countToken();
      } else {
        dbgSensorFmt("pulso FIN dur=%lums -> rearmar test", pulsoDur);
        armTestStandalone();
      }
#else
      if (motorOn && targetRemaining > 0) {
        dbgSensorFmt("pulso FIN dur=%lums -> contar TOKEN", pulsoDur);
        countToken();
      } else {
        dbgSensorFmt("pulso FIN dur=%lums SIN token (motor=%d target=%d)", pulsoDur, motorOn ? 1 : 0,
                     targetRemaining);
      }
#endif
    }
    lastSensorState = state;
  }
}

static void processTimeout(void) {
  if (!motorOn || targetRemaining <= 0) return;
  HopperConfig *h = activeHopper();
  unsigned long now = millis();
  float elapsed = (now - motorOnSinceMs) / 1000.0f;
  if (elapsed < h->timeoutMotorS) return;

  if (destrabeCfg.enabled && destrabeCfg.autoOnTimeout && h->motorRevPin >= 0 &&
      destrabeAttempts < destrabeCfg.maxIntentos &&
      (now - lastDestrabeMs) >= (unsigned long)(destrabeCfg.cooldownS * 1000.0f)) {
    destrabeAttempts++;
    lastDestrabeMs = now;
    setMotorState(false);
    doUnjam(destrabeCfg.retrocesoS);
    motorOnSinceMs = millis();
    return;
  }

  setMotorState(false);
  jammed = true;
  emitEventMsg("JAM", "timeout");
}

static void handleCommand(const char *line) {
  StaticJsonDocument<768> doc;
  if (deserializeJson(doc, line)) {
    StaticJsonDocument<96> err;
    err["dir"] = "evt";
    err["type"] = "ERR";
    err["message"] = "json_parse";
    serializeJson(err, Serial);
    Serial.println();
    return;
  }
  const char *type = doc["type"] | "";
  if (strcmp(type, "HELLO") == 0) {
    StaticJsonDocument<64> ack;
    ack["dir"] = "evt";
    ack["type"] = "HELLO_ACK";
    ack["v"] = 1;
    serializeJson(ack, Serial);
    Serial.println();
    return;
  }
  if (strcmp(type, "PING") == 0) {
    StaticJsonDocument<48> pong;
    pong["dir"] = "evt";
    pong["type"] = "PONG";
    serializeJson(pong, Serial);
    Serial.println();
    return;
  }
  if (strcmp(type, "CONFIG") == 0) {
    handleConfig(doc);
    return;
  }
  if (strcmp(type, "SET_TARGET") == 0) {
    handleSetTarget(doc["remaining"] | 0);
    return;
  }
  if (strcmp(type, "SELECT_HOPPER") == 0) {
    int hid = doc["id"] | 1;
    for (int i = 0; i < MAX_HOPPERS; i++) {
      if (hoppers[i].id == hid) {
        setMotorState(false);
        activeHopperIdx = i;
        applyHopperPins(&hoppers[i]);
        emitEvent("READY");
        return;
      }
    }
    return;
  }
  if (strcmp(type, "UNJAM") == 0) {
    float retro = doc["retroceso_s"] | destrabeCfg.retrocesoS;
    doUnjam(retro);
    return;
  }
  if (strcmp(type, "STOP") == 0) {
    dbg("MOTOR", "STOP cmd");
    targetRemaining = 0;
    setMotorState(false);
    emitEvent("RUN_DONE");
    return;
  }
  if (strcmp(type, "SIMULATE") == 0) {
    if (targetRemaining > 0) countToken();
    return;
  }
}

static void readSerial(void) {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      if (rxLen > 0) {
        rxLine[rxLen] = '\0';
        handleCommand(rxLine);
      }
      rxLen = 0;
      rxLine[0] = '\0';
    } else if (c != '\r') {
      if (rxLen < sizeof(rxLine) - 1) {
        rxLine[rxLen++] = c;
      } else {
        rxLen = 0;
      }
    }
  }
}

static void armTestStandalone(void) {
#if TEST_STANDALONE
  configReady = true;
  targetRemaining = TEST_FICHAS_INICIALES;
  jammed = false;
  activeHopper()->timeoutMotorS = DEFAULT_TIMEOUT_MOTOR_S;
  activeHopper()->motorRevPin = -1;
  dbgSensorFmt("TEST: %d fichas | LED pin=%d boton pin=%d (pulsa+suelta=1 ficha)",
               targetRemaining, activeHopper()->motorPin, activeHopper()->sensorPin);
  setMotorState(true);
  emitEvent("SYNC");
#endif
}

void setup(void) {
  forceRelaysOffSafe();
  Serial.begin(9600);
  targetRemaining = 0;
  motorOn = false;
  configReady = false;
  jammed = false;
  rxLen = 0;
  rxLine[0] = '\0';
  for (int i = 0; i < MAX_HOPPERS; i++) {
    initHopperDefaults(&hoppers[i], i + 1);
  }
  applyHopperPins(activeHopper());
  lastSensorState = digitalRead(activeHopper()->sensorPin);
  lastCountMs = 0;
#if TEST_STANDALONE
  testBootBlink();
#endif
  if (sensorDebugOn()) {
    dbgSensorFmt("BOOT pin=%d estado=%s(%d) DEBUG_SENSOR=%d bounce=%dms",
                 activeHopper()->sensorPin, lastSensorState == LOW ? "LOW" : "HIGH", lastSensorState,
                 DEBUG_SENSOR, activeHopper()->sensorBounceMs);
  }
#if TEST_STANDALONE
  armTestStandalone();
#endif
}

void loop(void) {
  readSerial();
  processSensor();
  if (configReady && targetRemaining > 0 && !jammed) {
    if (!motorOn) setMotorState(true);
    processTimeout();
  } else if (motorOn) {
    setMotorState(false);
  }
  delay(2);
}
