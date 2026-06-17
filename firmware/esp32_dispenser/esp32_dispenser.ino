/*
 * esp32_dispenser.ino — Expendedora (motor + sensor óptico)
 * Placa: Arduino Uno (USB nativo, 115200 baud, JSON por línea).
 * Protocolo PC (claves JSON en inglés): expendedora/logic/hardware/protocol.py
 *
 * Arduino IDE: Placa "Arduino Uno", librería ArduinoJson v7.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <stdarg.h>
#include <string.h>
#include "config.h"

/* --- Tipos de dominio (nombres en español) --- */

typedef struct {
  int id;
  int pinMotor;
  int pinMotorRev;
  int pinSensor;
  bool motorActivoBajo;
  bool sensorBloqueadoAlto;
  int reboteSensorMs;
  float pulsoMinS;
  float pulsoMaxS;
  float timeoutMotorS;
} ConfigTolva;

typedef struct {
  bool habilitado;
  bool autoEnTimeout;
  float retrocesoS;
  int maxIntentos;
  float enfriamientoS;
} ConfigDestrabe;

/* --- Estado global --- */

static ConfigTolva tolvas[MAX_HOPPERS];
static int indiceTolvaActiva = 0;
static ConfigDestrabe cfgDestrabe;
static int fichasRestantes = 0;
static bool motorEncendido = false;
static unsigned long motorEncendidoDesdeMs = 0;
static unsigned long motorArmadoDesdeMs = 0;
static const unsigned long GRACIA_SENSOR_MOTOR_MS = 180;
static const unsigned long SEPARACION_MINIMA_FICHA_MS = 120;
static int intentosDestrabe = 0;
static unsigned long ultimoDestrabeMs = 0;
static bool tolvaTrabada = false;
static bool configLista = false;
static bool depurarMotorSensor = false;
static unsigned long ultimoDepuracionSensorMs = 0;

static bool pulsoSensorActivo = false;
static unsigned long pulsoInicioMs = 0;
static unsigned long ultimoConteoMs = 0;
static int ultimoEstadoSensor = HIGH;
static bool destrabeEnCurso = false;
static bool modoPrueba = false;

static void procesarSensor(void);

static char lineaRx[513];
static size_t largoLineaRx = 0;

/* --- Tolvas --- */

static void initTolvaPorDefecto(ConfigTolva *t, int id) {
  t->id = id;
  t->pinMotor = DEFAULT_MOTOR_PIN;
  t->pinMotorRev = DEFAULT_MOTOR_REV_PIN;
  t->pinSensor = DEFAULT_SENSOR_PIN;
  t->motorActivoBajo = (DEFAULT_MOTOR_ACTIVE_LOW != 0);
  t->sensorBloqueadoAlto = (DEFAULT_SENSOR_BLOCKED_HIGH != 0);
  t->reboteSensorMs = DEFAULT_SENSOR_BOUNCE_MS;
  t->pulsoMinS = DEFAULT_PULSO_MIN_S;
  t->pulsoMaxS = DEFAULT_PULSO_MAX_S;
  t->timeoutMotorS = DEFAULT_TIMEOUT_MOTOR_S;
}

static ConfigTolva *tolvaActiva(void) {
  return &tolvas[indiceTolvaActiva];
}

/* --- Depuración --- */

static void depurar(const char *categoria, const char *mensaje) {
  if (!depurarMotorSensor) return;
  Serial.print("[DBG ");
  Serial.print(categoria);
  Serial.print("] ");
  Serial.println(mensaje);
}

static void depurarFmt(const char *categoria, const char *fmt, ...) {
  if (!depurarMotorSensor) return;
  char buf[96];
  va_list args;
  va_start(args, fmt);
  vsnprintf(buf, sizeof(buf), fmt, args);
  va_end(args);
  depurar(categoria, buf);
}

static bool depuracionSensorActiva(void) {
  return (DEBUG_SENSOR != 0) || depurarMotorSensor;
}

static void depurarSensor(const char *mensaje) {
  if (!depuracionSensorActiva()) return;
  Serial.print("[DBG SENSOR] ");
  Serial.println(mensaje);
}

static void depurarSensorFmt(const char *fmt, ...) {
  if (!depuracionSensorActiva()) return;
  char buf[128];
  va_list args;
  va_start(args, fmt);
  vsnprintf(buf, sizeof(buf), fmt, args);
  va_end(args);
  depurarSensor(buf);
}

/* --- Motor y relés --- */

static int nivelMotorEncendido(const ConfigTolva *t) {
  return t->motorActivoBajo ? LOW : HIGH;
}

static int nivelMotorApagado(const ConfigTolva *t) {
  return t->motorActivoBajo ? HIGH : LOW;
}

static void emitirEvento(const char *tipo) {
  StaticJsonDocument<192> doc;
  doc["dir"] = "evt";
  doc["type"] = tipo;
  doc["hopper_id"] = tolvaActiva()->id;
  doc["remaining"] = fichasRestantes;
  serializeJson(doc, Serial);
  Serial.println();
}

static void emitirEventoConMensaje(const char *tipo, const char *mensaje) {
  StaticJsonDocument<192> doc;
  doc["dir"] = "evt";
  doc["type"] = tipo;
  doc["hopper_id"] = tolvaActiva()->id;
  doc["remaining"] = fichasRestantes;
  doc["message"] = mensaje;
  serializeJson(doc, Serial);
  Serial.println();
}

static void motorAdelante(const ConfigTolva *t) {
  if (t->pinMotorRev >= 0) digitalWrite(t->pinMotorRev, nivelMotorApagado(t));
  digitalWrite(t->pinMotor, nivelMotorEncendido(t));
}

static void motorAtras(const ConfigTolva *t) {
  digitalWrite(t->pinMotor, nivelMotorApagado(t));
  if (t->pinMotorRev >= 0) digitalWrite(t->pinMotorRev, nivelMotorEncendido(t));
}

static void motorApagarPines(const ConfigTolva *t) {
  digitalWrite(t->pinMotor, nivelMotorApagado(t));
  if (t->pinMotorRev >= 0) digitalWrite(t->pinMotorRev, nivelMotorApagado(t));
}

#if TEST_STANDALONE
static void escribirLedPrueba(bool encendido) {
  pinMode(TEST_LED_PIN, OUTPUT);
  int nivel = encendido ? (TEST_LED_ACTIVE_HIGH ? HIGH : LOW) : (TEST_LED_ACTIVE_HIGH ? LOW : HIGH);
  digitalWrite(TEST_LED_PIN, nivel);
  if (depuracionSensorActiva()) {
    depurarSensorFmt("LED GPIO%d -> %s (write=%d read=%d)", TEST_LED_PIN, encendido ? "ON" : "OFF", nivel,
                     digitalRead(TEST_LED_PIN));
  }
}

static void parpadeoArranquePrueba(void) {
#if TEST_BOOT_BLINK
  pinMode(TEST_LED_PIN, OUTPUT);
  for (int i = 0; i < 5; i++) {
    escribirLedPrueba(true);
    delay(200);
    escribirLedPrueba(false);
    delay(200);
  }
  if (depuracionSensorActiva()) {
    depurarSensorFmt("BOOT blink listo en GPIO%d (ACTIVE_HIGH=%d)", TEST_LED_PIN, TEST_LED_ACTIVE_HIGH);
  }
#endif
}
#endif

static void aplicarSalidaMotor(const ConfigTolva *t, bool encender) {
#if TEST_STANDALONE
  (void)t;
  escribirLedPrueba(encender);
#else
  if (encender) {
    motorAdelante(t);
  } else {
    motorApagarPines(t);
  }
#endif
}

static void forzarRelesApagadosSeguro(void) {
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

static void setEstadoMotor(bool encender) {
  ConfigTolva *t = tolvaActiva();
  if (encender && !configLista) {
    depurar("MOTOR", "encender bloqueado: sin CONFIG");
    return;
  }
  if (encender == motorEncendido) return;
  motorEncendido = encender;
  if (encender) {
    depurarFmt("MOTOR", "ON pin=%d rev=%d objetivo=%d", t->pinMotor, t->pinMotorRev, fichasRestantes);
    aplicarSalidaMotor(t, true);
    motorEncendidoDesdeMs = millis();
    motorArmadoDesdeMs = millis();
    emitirEvento("MOTOR_ON");
  } else {
    depurarFmt("MOTOR", "OFF pin=%d objetivo=%d", t->pinMotor, fichasRestantes);
    aplicarSalidaMotor(t, false);
    emitirEvento("MOTOR_OFF");
  }
}

static void aplicarPinesTolva(const ConfigTolva *t) {
#if !TEST_STANDALONE
  pinMode(t->pinMotor, OUTPUT);
  digitalWrite(t->pinMotor, nivelMotorApagado(t));
  delay(5);
  digitalWrite(t->pinMotor, nivelMotorApagado(t));
  if (t->pinMotorRev >= 0) {
    pinMode(t->pinMotorRev, OUTPUT);
    digitalWrite(t->pinMotorRev, nivelMotorApagado(t));
    delay(5);
    digitalWrite(t->pinMotorRev, nivelMotorApagado(t));
  }
#endif
  pinMode(t->pinSensor, t->sensorBloqueadoAlto ? INPUT : INPUT_PULLUP);
}

static void cargarTolvaDesdeJson(JsonObject hopper, int idx) {
  if (idx < 0 || idx >= MAX_HOPPERS) return;
  ConfigTolva *t = &tolvas[idx];
  t->id = hopper["id"] | (idx + 1);
  t->pinMotor = hopper["motor_pin"] | DEFAULT_MOTOR_PIN;
  if (!hopper["motor_pin_rev"].isNull()) {
    t->pinMotorRev = hopper["motor_pin_rev"].as<int>();
  } else {
    t->pinMotorRev = -1;
  }
  t->pinSensor = hopper["sensor_pin"] | DEFAULT_SENSOR_PIN;
  t->motorActivoBajo = hopper["motor_active_low"] | true;
  t->sensorBloqueadoAlto = hopper["sensor_blocked_high"].isNull()
                               ? (DEFAULT_SENSOR_BLOCKED_HIGH != 0)
                               : hopper["sensor_blocked_high"].as<bool>();
  t->reboteSensorMs = hopper["sensor_bouncetime_ms"] | DEFAULT_SENSOR_BOUNCE_MS;
  JsonObject cal = hopper["calibracion"];
  if (!cal.isNull()) {
    t->pulsoMinS = cal["pulso_min_s"] | DEFAULT_PULSO_MIN_S;
    t->pulsoMaxS = cal["pulso_max_s"] | DEFAULT_PULSO_MAX_S;
    t->timeoutMotorS = cal["timeout_motor_s"] | DEFAULT_TIMEOUT_MOTOR_S;
  } else {
    t->pulsoMinS = DEFAULT_PULSO_MIN_S;
    t->pulsoMaxS = DEFAULT_PULSO_MAX_S;
    t->timeoutMotorS = DEFAULT_TIMEOUT_MOTOR_S;
  }
  if (t->reboteSensorMs <= 0) t->reboteSensorMs = DEFAULT_SENSOR_BOUNCE_MS;
  aplicarPinesTolva(t);
}

/* --- Comandos CONFIG / SET_TARGET --- */

static void manejarConfig(JsonDocument &doc) {
  if (doc["hopper"].is<JsonObject>()) {
    cargarTolvaDesdeJson(doc["hopper"].as<JsonObject>(), indiceTolvaActiva);
  }
  if (doc["hoppers"].is<JsonArray>()) {
    JsonArray arr = doc["hoppers"].as<JsonArray>();
    int i = 0;
    for (JsonObject obj : arr) {
      cargarTolvaDesdeJson(obj, i);
      i++;
      if (i >= MAX_HOPPERS) break;
    }
  }
  if (doc["destrabe"].is<JsonObject>()) {
    JsonObject d = doc["destrabe"];
    cfgDestrabe.habilitado = d["enabled"] | true;
    cfgDestrabe.autoEnTimeout = d["auto_on_timeout"] | true;
    cfgDestrabe.retrocesoS = d["retroceso_s"] | 1.5f;
    cfgDestrabe.maxIntentos = d["max_intentos"] | 3;
    cfgDestrabe.enfriamientoS = d["cooldown_s"] | 2.0f;
  }
  if (doc["debug"].is<bool>()) depurarMotorSensor = doc["debug"].as<bool>();
  tolvaTrabada = false;
  intentosDestrabe = 0;
#if TEST_STANDALONE
  armarPruebaStandalone();
#else
  fichasRestantes = 0;
  configLista = true;
  setEstadoMotor(false);
#endif
  ultimoEstadoSensor = digitalRead(tolvaActiva()->pinSensor);
  depurarFmt("CONFIG", "sensor pin=%d blocked_high=%d (libre=0 tapado=1) raw=%s",
               tolvaActiva()->pinSensor, tolvaActiva()->sensorBloqueadoAlto ? 1 : 0,
               ultimoEstadoSensor == LOW ? "LOW(0)" : "HIGH(1)");
  depurar("CONFIG", depurarMotorSensor ? "READY debug=ON" : "READY debug=OFF");
  emitirEvento("READY");
}

static void manejarObjetivoFichas(int restantes) {
  if (!configLista) {
    depurar("MOTOR", "SET_TARGET ignorado: sin CONFIG");
    return;
  }
  depurarFmt("MOTOR", "SET_TARGET %d -> %d", fichasRestantes, max(0, restantes));
  fichasRestantes = max(0, restantes);
  modoPrueba = false;
  tolvaTrabada = false;
  pulsoSensorActivo = false;
  ultimoEstadoSensor = digitalRead(tolvaActiva()->pinSensor);
  ultimoConteoMs = millis();
  if (fichasRestantes > 0) {
    setEstadoMotor(true);
  } else {
    setEstadoMotor(false);
    emitirEvento("RUN_DONE");
  }
  emitirEvento("SYNC");
}

static void ejecutarDestrabe(float retrocesoS) {
  ConfigTolva *t = tolvaActiva();
  setEstadoMotor(false);
  if (t->pinMotorRev < 0) {
    emitirEvento("UNJAM_DONE");
    return;
  }
  destrabeEnCurso = true;
  motorAtras(t);
  unsigned long finRetrocesoMs = millis() + (unsigned long)(retrocesoS * 1000.0f);
  while (millis() < finRetrocesoMs) {
    procesarSensor();
    delay(2);
  }
  motorApagarPines(t);
  destrabeEnCurso = false;
  tolvaTrabada = false;
  emitirEvento("UNJAM_DONE");
  if (fichasRestantes > 0) setEstadoMotor(true);
}

static void contarFicha(void) {
  if (fichasRestantes <= 0) return;
  ConfigTolva *t = tolvaActiva();
  unsigned long ahora = millis();
  unsigned long separacionMin = (unsigned long)(t->pulsoMinS * 1000.0f);
  if (separacionMin < SEPARACION_MINIMA_FICHA_MS) separacionMin = SEPARACION_MINIMA_FICHA_MS;
  if (t->reboteSensorMs > (int)separacionMin) separacionMin = (unsigned long)t->reboteSensorMs;
  if (ultimoConteoMs > 0 && (ahora - ultimoConteoMs) < separacionMin) {
    depurarSensorFmt("TOKEN rechazado gap=%lu ms (min=%lu)", (unsigned long)(ahora - ultimoConteoMs), separacionMin);
    return;
  }
  fichasRestantes--;
  depurarSensorFmt("TOKEN OK restantes=%d pulso_ms=%lu", fichasRestantes,
                   pulsoInicioMs > 0 ? (unsigned long)(ahora - pulsoInicioMs) : 0UL);
  ultimoConteoMs = millis();
  motorEncendidoDesdeMs = millis();
  tolvaTrabada = false;
  if (modoPrueba) {
    emitirEvento("TEST_TOKEN");
    modoPrueba = false;
  } else {
    emitirEvento("TOKEN");
  }
  if (fichasRestantes <= 0) {
    setEstadoMotor(false);
    emitirEvento("RUN_DONE");
#if TEST_STANDALONE
    depurarSensor("TEST: lote terminado -> reinicio automatico");
    armarPruebaStandalone();
#endif
  }
}

static int ultimoEstadoDepurado = -1;

static void depurarSensorPeriodico(int estadoRaw, unsigned long ahora) {
  if (!depuracionSensorActiva()) return;
  bool activo = motorEncendido || destrabeEnCurso || fichasRestantes > 0 || pulsoSensorActivo;
  bool cambio = (estadoRaw != ultimoEstadoDepurado);
  if (!activo && !cambio) return;
  if (activo && (ahora - ultimoDepuracionSensorMs) < (unsigned long)DEBUG_SENSOR_INTERVAL_MS) return;
  ultimoDepuracionSensorMs = ahora;
  ultimoEstadoDepurado = estadoRaw;
  ConfigTolva *t = tolvaActiva();
  unsigned long graciaRestante = 0;
  if (motorEncendido && fichasRestantes > 0 && ahora >= motorArmadoDesdeMs) {
    unsigned long transcurrido = ahora - motorArmadoDesdeMs;
    if (transcurrido < GRACIA_SENSOR_MOTOR_MS) graciaRestante = GRACIA_SENSOR_MOTOR_MS - transcurrido;
  }
  unsigned long desdeUltimaFicha = ultimoConteoMs > 0 ? ahora - ultimoConteoMs : 0;
  depurarSensorFmt(
      "pin=%d raw=%s(%d) motor=%d obj=%d pulso=%d gracia=%lums desde_ficha=%lums rebote=%dms",
      t->pinSensor, estadoRaw == LOW ? "LOW" : "HIGH", estadoRaw, motorEncendido ? 1 : 0, fichasRestantes,
      pulsoSensorActivo ? 1 : 0, graciaRestante, desdeUltimaFicha, t->reboteSensorMs);
}

static bool esFlancoInicioPulso(const ConfigTolva *t, int prev, int cur) {
  if (t->sensorBloqueadoAlto) return prev == LOW && cur == HIGH;
  return prev == HIGH && cur == LOW;
}

static bool esFlancoFinPulso(const ConfigTolva *t, int prev, int cur) {
  if (t->sensorBloqueadoAlto) return prev == HIGH && cur == LOW;
  return prev == LOW && cur == HIGH;
}

static void procesarSensor(void) {
  ConfigTolva *t = tolvaActiva();
  int estado = digitalRead(t->pinSensor);
  unsigned long ahora = millis();
  depurarSensorPeriodico(estado, ahora);
#if TEST_STANDALONE
#else
  if (motorEncendido && fichasRestantes > 0 && (ahora - motorArmadoDesdeMs) < GRACIA_SENSOR_MOTOR_MS) {
    if (estado != ultimoEstadoSensor) {
      depurarSensorFmt("flanco %d->%d IGNORADO (gracia motor %lums)", ultimoEstadoSensor, estado,
                       (unsigned long)(GRACIA_SENSOR_MOTOR_MS - (ahora - motorArmadoDesdeMs)));
    }
    return;
  }
#endif
  if (estado != ultimoEstadoSensor) {
    depurarSensorFmt("flanco %d->%d motor=%d obj=%d pulso_activo=%d blocked_high=%d", ultimoEstadoSensor, estado,
                     motorEncendido ? 1 : 0, fichasRestantes, pulsoSensorActivo ? 1 : 0,
                     t->sensorBloqueadoAlto ? 1 : 0);
    if (esFlancoInicioPulso(t, ultimoEstadoSensor, estado)) {
      float sepMin = (float)t->reboteSensorMs;
      if (sepMin < 120.0f) sepMin = 120.0f;
      float pulsoMs = t->pulsoMinS * 1000.0f;
      if (pulsoMs > sepMin) sepMin = pulsoMs;
      if (ultimoConteoMs == 0 || (ahora - ultimoConteoMs) >= (unsigned long)sepMin) {
        pulsoSensorActivo = true;
        pulsoInicioMs = ahora;
        depurarSensorFmt("pulso INICIO (sep_min=%dms)", (int)sepMin);
      } else {
        depurarSensorFmt("inicio pulso ignorado: muy pronto tras ultima ficha (%lums < %dms)",
                         (unsigned long)(ahora - ultimoConteoMs), (int)sepMin);
      }
    } else if (pulsoSensorActivo && esFlancoFinPulso(t, ultimoEstadoSensor, estado)) {
      unsigned long duracionPulso = ahora - pulsoInicioMs;
      pulsoSensorActivo = false;
#if TEST_STANDALONE
      if (fichasRestantes > 0) {
        depurarSensorFmt("pulso FIN dur=%lums -> contar TOKEN (test)", duracionPulso);
        contarFicha();
      } else {
        depurarSensorFmt("pulso FIN dur=%lums -> rearmar test", duracionPulso);
        armarPruebaStandalone();
      }
#else
      if ((motorEncendido || destrabeEnCurso) && fichasRestantes > 0) {
        depurarSensorFmt("pulso FIN dur=%lums -> contar TOKEN", duracionPulso);
        contarFicha();
      } else {
        depurarSensorFmt("pulso FIN dur=%lums SIN token (motor=%d obj=%d)", duracionPulso, motorEncendido ? 1 : 0,
                         fichasRestantes);
      }
#endif
    }
    ultimoEstadoSensor = estado;
  }
}

static void procesarTimeoutMotor(void) {
  if (!motorEncendido || fichasRestantes <= 0) return;
  ConfigTolva *t = tolvaActiva();
  unsigned long ahora = millis();
  float segundosEncendido = (ahora - motorEncendidoDesdeMs) / 1000.0f;
  if (segundosEncendido < t->timeoutMotorS) return;

  if (cfgDestrabe.habilitado && cfgDestrabe.autoEnTimeout && t->pinMotorRev >= 0 &&
      intentosDestrabe < cfgDestrabe.maxIntentos &&
      (ahora - ultimoDestrabeMs) >= (unsigned long)(cfgDestrabe.enfriamientoS * 1000.0f)) {
    intentosDestrabe++;
    ultimoDestrabeMs = ahora;
    setEstadoMotor(false);
    ejecutarDestrabe(cfgDestrabe.retrocesoS);
    motorEncendidoDesdeMs = millis();
    return;
  }

  setEstadoMotor(false);
  tolvaTrabada = true;
  modoPrueba = false;
  emitirEventoConMensaje("JAM", "timeout");
}

static void manejarComando(const char *linea) {
  StaticJsonDocument<768> doc;
  if (deserializeJson(doc, linea)) {
    StaticJsonDocument<96> err;
    err["dir"] = "evt";
    err["type"] = "ERR";
    err["message"] = "json_parse";
    serializeJson(err, Serial);
    Serial.println();
    return;
  }
  const char *tipo = doc["type"] | "";
  if (strcmp(tipo, "HELLO") == 0) {
    StaticJsonDocument<64> ack;
    ack["dir"] = "evt";
    ack["type"] = "HELLO_ACK";
    ack["v"] = 1;
    serializeJson(ack, Serial);
    Serial.println();
    return;
  }
  if (strcmp(tipo, "PING") == 0) {
    StaticJsonDocument<48> pong;
    pong["dir"] = "evt";
    pong["type"] = "PONG";
    serializeJson(pong, Serial);
    Serial.println();
    return;
  }
  if (strcmp(tipo, "CONFIG") == 0) {
    manejarConfig(doc);
    return;
  }
  if (strcmp(tipo, "SET_TARGET") == 0) {
    manejarObjetivoFichas(doc["remaining"] | 0);
    return;
  }
  if (strcmp(tipo, "SELECT_HOPPER") == 0) {
    int idTolva = doc["id"] | 1;
    for (int i = 0; i < MAX_HOPPERS; i++) {
      if (tolvas[i].id == idTolva) {
        setEstadoMotor(false);
        indiceTolvaActiva = i;
        aplicarPinesTolva(&tolvas[i]);
        emitirEvento("READY");
        return;
      }
    }
    return;
  }
  if (strcmp(tipo, "UNJAM") == 0) {
    float retroceso = doc["retroceso_s"] | cfgDestrabe.retrocesoS;
    ejecutarDestrabe(retroceso);
    return;
  }
  if (strcmp(tipo, "TEST_DISPENSE") == 0) {
    depurar("MOTOR", "TEST_DISPENSE cmd");
    intentosDestrabe = 0;
    tolvaTrabada = false;
    fichasRestantes = 1;
    modoPrueba = true;
    setEstadoMotor(true);
    return;
  }
  if (strcmp(tipo, "STOP") == 0) {
    depurar("MOTOR", "STOP cmd");
    fichasRestantes = 0;
    modoPrueba = false;
    setEstadoMotor(false);
    emitirEvento("RUN_DONE");
    return;
  }
  if (strcmp(tipo, "SIMULATE") == 0) {
    if (fichasRestantes > 0) contarFicha();
    return;
  }
}

static void leerSerial(void) {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      if (largoLineaRx > 0) {
        lineaRx[largoLineaRx] = '\0';
        manejarComando(lineaRx);
      }
      largoLineaRx = 0;
      lineaRx[0] = '\0';
    } else if (c != '\r') {
      if (largoLineaRx < sizeof(lineaRx) - 1) {
        lineaRx[largoLineaRx++] = c;
      } else {
        largoLineaRx = 0;
      }
    }
  }
}

static void armarPruebaStandalone(void) {
#if TEST_STANDALONE
  configLista = true;
  fichasRestantes = TEST_FICHAS_INICIALES;
  tolvaTrabada = false;
  tolvaActiva()->timeoutMotorS = DEFAULT_TIMEOUT_MOTOR_S;
  tolvaActiva()->pinMotorRev = -1;
  depurarSensorFmt("TEST: %d fichas | LED pin=%d boton pin=%d (pulsa+suelta=1 ficha)",
                   fichasRestantes, tolvaActiva()->pinMotor, tolvaActiva()->pinSensor);
  setEstadoMotor(true);
  emitirEvento("SYNC");
#endif
}

void setup(void) {
  forzarRelesApagadosSeguro();
  Serial.begin(115200);
  fichasRestantes = 0;
  motorEncendido = false;
  configLista = false;
  tolvaTrabada = false;
  largoLineaRx = 0;
  lineaRx[0] = '\0';
  for (int i = 0; i < MAX_HOPPERS; i++) {
    initTolvaPorDefecto(&tolvas[i], i + 1);
  }
  aplicarPinesTolva(tolvaActiva());
  ultimoEstadoSensor = digitalRead(tolvaActiva()->pinSensor);
  ultimoConteoMs = 0;
#if TEST_STANDALONE
  parpadeoArranquePrueba();
#endif
  if (depuracionSensorActiva()) {
    depurarSensorFmt("BOOT pin=%d blocked_high=%d estado=%s(%d) (libre=0 tapado=1)",
                     tolvaActiva()->pinSensor, tolvaActiva()->sensorBloqueadoAlto ? 1 : 0,
                     ultimoEstadoSensor == LOW ? "LOW" : "HIGH", ultimoEstadoSensor);
  }
#if TEST_STANDALONE
  armarPruebaStandalone();
#endif
}

void loop(void) {
  leerSerial();
  procesarSensor();
  if (configLista && fichasRestantes > 0 && !tolvaTrabada) {
    if (!motorEncendido) setEstadoMotor(true);
    procesarTimeoutMotor();
  } else if (motorEncendido) {
    setEstadoMotor(false);
  }
  delay(2);
}
