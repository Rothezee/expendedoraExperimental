# Sistema de Expendedora de Fichas

Este repositorio contiene el software para un sistema de control de una máquina expendedora de fichas, diseñado para operar en una Raspberry Pi. El sistema gestiona la lógica del motor, el conteo de fichas mediante un sensor óptico, y se comunica con un backend para el registro de operaciones.

## ✨ Características Principales

- **Control Automático del Motor**: El motor se activa automáticamente cuando hay fichas pendientes por entregar y se detiene cuando el contador llega a cero.
- **Conteo Preciso de Fichas**: Utiliza un sistema de detección de pulso completo (HIGH -> LOW -> HIGH) para evitar rebotes del sensor y contar cada ficha de manera fiable.
- **Interfaz Gráfica (GUI)**: Permite a los operadores gestionar la máquina, agregar fichas y ver contadores en tiempo real.
- **Registro de Operaciones**: Guarda un registro local (`registro.json`) de todas las transacciones, incluyendo fichas expendidas y dinero ingresado.
- **Comunicación con Servidor**: Envía reportes de ventas y pulsos de "heartbeat" a un servidor backend para monitoreo centralizado.
- **Modo Kiosk Seguro**: Incluye scripts para configurar un usuario "cajero" con acceso restringido, ideal para un entorno de producción.
- **Operación Offline Garantizada**: El sistema continúa dispensando fichas con normalidad ante cortes de internet; los reportes se reintentan en segundo plano sin bloquear la operación.

---

## 🏗️ Arquitectura del Sistema

El proyecto se compone de varias capas que trabajan en conjunto:

1.  **UI (`expendedora_gui.py`)**: Capa de presentación Tkinter para operación diaria.
2.  **Core (`expendedora_core.py`)**: Control de hardware (motor/sensor) y coordinación de telemetría.
3.  **Estado (`shared_buffer.py`)**: Estado compartido thread-safe encapsulado en `MachineState`.
4.  **Infraestructura (`infra/`)**:
    - `ConfigRepository`: normalización y persistencia de `config.json`.
    - `TelemetryClient`: armado/envío de heartbeat y telemetría HTTP.
    - `AuthRepositoryMySQL`: autenticación y alta de cajeros en MySQL.
5.  **Servicios (`services/`)**:
    - `CounterService`: esquema único de contadores y reglas de actividad.
    - `SessionService`: payloads de apertura/cierre/subcierre.
6.  **Dominio (`domain/`)**: modelos `dataclass` para reducir diccionarios sueltos.
7.  **Backend (PHP)**: recepción y persistencia centralizada.

---

## 🚀 Instalación y Puesta en Marcha

La configuración del sistema se divide en la preparación del entorno y la ejecución de la aplicación.

### 1. Configuración del Entorno (Modo Kiosk)

Para preparar la Raspberry Pi para un uso seguro en producción, se ha diseñado un sistema de usuario "cajero" con privilegios limitados. Este modo restringe el acceso al sistema operativo y ejecuta la aplicación de la expendedora automáticamente.

Toda la información detallada sobre cómo crear este usuario, aplicar las restricciones y solucionar problemas se encuentra en el siguiente documento:

➡️ **Guía de Configuración de Usuario Cajero**

Los scripts para automatizar esta configuración se encuentran en la carpeta `configSO/`.

### 2. Ejecución de la Aplicación

Una vez configurado el entorno, la aplicación principal se puede iniciar ejecutando:

```bash
python3 main.py
```

Si se ha configurado el modo kiosk, la aplicación se iniciará automáticamente al encender la Raspberry Pi.

---

## 🔄 Actualización remota automática

Se incluyó un updater cross-platform en `updater/auto_updater.py` para actualizar desde `origin/main`.

### Configuración (`config.json`)

Usa la sección:

```json
"updater": {
  "enabled": false,
  "remote": "origin",
  "branch": "main",
  "check_interval_s": 300,
  "run_pip_install": false,
  "requirements_file": "requirements.txt",
  "restart_command_linux": "",
  "restart_command_windows": "",
  "preserve_files": ["config.json", "registro.json", "buffer_state.json"]
}
```

Notas:
- `enabled=true` permite que el updater aplique cambios.
- `preserve_files` restaura esos archivos locales luego del `git reset --hard`.
- Define `restart_command_*` para reiniciar la app/servicio automáticamente tras update.

### Linux (Raspberry/MiniPC Linux)

1. Prueba manual:
   - `bash updater/run_update_linux.sh`
2. Instalación automática con systemd timer:
   - `sudo bash updater/systemd/install_updater_timer.sh`

Archivos incluidos:
- `updater/systemd/expendedora-updater.service`
- `updater/systemd/expendedora-updater.timer`

### Windows (MiniPC)

1. Prueba manual:
   - `powershell -ExecutionPolicy Bypass -File updater/run_update_windows.ps1`
2. Registro de tarea programada (cada 5 min):
   - `powershell -ExecutionPolicy Bypass -File updater/windows/register_updater_task.ps1`

La tarea se registra como `ExpendedoraAutoUpdater`.

---

## ⚙️ Funcionamiento del Motor y Sensor

El corazón del hardware es el sistema de control del motor, que se basa en el contador de fichas pendientes. El sensor óptico es responsable de decrementar este contador a medida que las fichas son dispensadas.

Para una explicación técnica detallada sobre la lógica del motor, la detección de pulsos del sensor y cómo se evitan los problemas de rebote, consulta el siguiente documento:

➡️ **Documentación del Sistema de Motor**

---

## ⚡ Optimizaciones de Rendimiento

Las siguientes mejoras fueron implementadas para garantizar operación estable en el hardware de la Raspberry Pi (especialmente en SD card) y ante condiciones de red inestable.

### Comunicación de Red No-Bloqueante

**Problema:** Todas las llamadas HTTP (`requests.post`) hacia el servidor remoto y local se ejecutaban de forma síncrona en el hilo principal. Ante un corte de internet, Python esperaba el timeout del sistema operativo (60-120 segundos), congelando completamente la GUI y el dispensado de fichas.

**Solución aplicada en `expendedora_core.py` y `expendedora_gui.py`:**
- Se agregó `timeout=5` a todos los `requests.post()`.
- El reporte de venta (`enviar_datos_venta_servidor`) que se ejecutaba al apagarse el motor ahora corre en un hilo separado (`daemon=True`), liberando el loop de control del motor inmediatamente.
- Todos los reportes de la GUI (apertura, cierre, subcierre, cerrar sesión) fueron migrados a una función helper `_post_en_hilo()` que despacha cada request en su propio hilo. La GUI responde instantáneamente independientemente del estado de la red.

### Escritura a Disco con Debounce (SD Card)

**Problema:** Por cada ficha dispensada se realizaban múltiples operaciones de escritura a disco: `actualizar_registro()` en el core hacía 2 lecturas + 1 escritura de `registro.json`, y `guardar_configuracion()` en la GUI escribía `config.json`. En una SD card de Raspberry Pi cada escritura puede tomar 50-200ms, frenando el hilo del motor y pudiendo perder pulsos del sensor.

**Solución aplicada:**

En `expendedora_core.py`, `actualizar_registro()` ahora acumula los cambios en memoria y los escribe al disco **una sola vez** tras 2 segundos de inactividad (debounce). Si se dispensan 20 fichas seguidas, se hace 1 escritura en lugar de 20. Al apagarse el sistema (`detener_sistema()`), se fuerza un flush para no perder datos.

```
Antes:  20 fichas → 20 escrituras a disco (20 × ~100ms = ~2 segundos bloqueados)
Después: 20 fichas → 1 escritura a disco (2 segundos después de la última ficha)
```

En `expendedora_gui.py`, `guardar_configuracion()` aplica el mismo patrón con un timer de 1.5 segundos. Las operaciones críticas (cierres, apertura, configuraciones manuales, cerrar sesión) usan `inmediato=True` para escribir al disco de forma garantizada e inmediata.

### Anti-flood de Callbacks GUI

**Problema:** El core llama a `sincronizar_desde_core()` por cada ficha detectada. Si el motor dispensa rápido, se encolaban múltiples callbacks en `root.after()` antes de que Tkinter procesara el primero, provocando lentitud acumulativa en la interfaz.

**Solución aplicada en `expendedora_gui.py`:** Se agregó el flag `_after_sincronizar_pendiente`. Mientras haya un callback en la cola de Tkinter, las llamadas adicionales se descartan. Cuando el callback se ejecuta, lee el valor **actual** del buffer (no el del momento en que fue encolado), por lo que no se pierde ninguna actualización.

### Corrección de Labels con Formato Incorrecto

**Problema:** Los métodos `procesar_expender_fichas`, `procesar_devolucion_fichas`, `procesar_cambio_fichas` y `simular_promo` actualizaban labels con prefijos de texto (`"Fichas Restantes: X"`, `"Dinero ingresado: $X"`) cuando los widgets fueron creados para mostrar solo el valor numérico. Esto causaba que los displays se vieran corrompidos hasta que el callback del core los pisaba con el formato correcto.

---

## 🔧 Solución de Problemas

Si encuentras problemas como el motor no se detiene, las fichas no se cuentan correctamente o la GUI no se actualiza, hemos preparado una guía específica con las causas más comunes y sus soluciones.

➡️ **Guía de Solución de Problemas**

---

## 📁 Estructura del Repositorio

```
expendedoraExperimental/
├── domain/
│   └── models.py             # Dataclasses de dominio.
├── infra/
│   ├── auth_repository_mysql.py # Repositorio de autenticación MySQL.
│   ├── config_repository.py  # Configuración y migración de config.
│   └── telemetry_client.py   # Cliente HTTP para api_receptor.
├── services/
│   ├── counter_service.py    # Utilidades/validaciones de contadores.
│   └── session_service.py    # Construcción de payloads de cierre.
├── expendedora_core.py     # Lógica principal del motor y sensor.
├── expendedora_gui.py      # Interfaz gráfica para el operador.
├── shared_buffer.py        # Estado compartido thread-safe.
├── main.py                 # Punto de entrada de la aplicación.
├── config.json             # Config API/MySQL/máquina + contadores.
├── registro.json           # Registro de ventas y operaciones.
├── tests/                  # Pruebas unitarias y smoke tests.
├── configSO/               # Scripts para configurar el SO (modo kiosk).
│   ├── crear_usuario_cajero.sh
│   └── restricciones_cajero.sh
└── Notas/                  # Documentación detallada del proyecto.
    ├── USUARIO_CAJERO_README.md
    ├── SISTEMA_MOTOR.md
    └── SOLUCION_PROBLEMAS.md
```
