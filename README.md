# Sistema de Expendedora de Fichas

Este repositorio contiene el software para un sistema de control de una máquina expendedora de fichas, diseñado para operar en una Raspberry Pi. El sistema gestiona la lógica del motor, el conteo de fichas mediante un sensor óptico, y se comunica con un backend para el registro de operaciones.

## ✨ Características Principales

- **Control Automático del Motor**: El motor se activa automáticamente cuando hay fichas pendientes por entregar y se detiene cuando el contador llega a cero.
- **Conteo Preciso de Fichas**: Utiliza un sistema de detección de pulso completo (HIGH -> LOW -> HIGH) para evitar rebotes del sensor y contar cada ficha de manera fiable.
- **Interfaz Gráfica (GUI)**: Permite a los operadores gestionar la máquina, agregar fichas y ver contadores en tiempo real.
- **Registro de Operaciones**: Guarda un registro local (`registro.json`) de todas las transacciones, incluyendo fichas expendidas y dinero ingresado.
- **Comunicación con Servidor**: Envía reportes de ventas y pulsos de "heartbeat" a un servidor backend para monitoreo centralizado.
- **Modo Kiosk Seguro**: Incluye scripts para configurar un usuario "cajero" con acceso restringido, ideal para un entorno de producción.

---

## 🏗️ Arquitectura del Sistema

El proyecto se compone de varias partes que trabajan en conjunto:

1.  **Core de la Expendedora (`expendedora_core.py`)**: Es el cerebro del sistema que corre en la Raspberry Pi. Controla el hardware (motor y sensor) a través de los pines GPIO.
2.  **Interfaz Gráfica (`expendedora_gui.py`)**: La aplicación de escritorio (probablemente Tkinter) que el operador utiliza para interactuar con la máquina.
3.  **Buffer Compartido (`shared_buffer.py`)**: Un módulo crucial que gestiona la comunicación segura (thread-safe) entre la GUI y el core del motor.
4.  **Scripts de Configuración (`configSO/`)**: Scripts de Bash para preparar el sistema operativo de la Raspberry Pi, creando un usuario restringido para la operación segura de la máquina.
5.  **Backend (PHP)**: Un servidor web que recibe datos de la expendedora, como reportes de ventas y cierres diarios.

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

## ⚙️ Funcionamiento del Motor y Sensor

El corazón del hardware es el sistema de control del motor, que se basa en el contador de fichas pendientes. El sensor óptico es responsable de decrementar este contador a medida que las fichas son dispensadas.

Para una explicación técnica detallada sobre la lógica del motor, la detección de pulsos del sensor y cómo se evitan los problemas de rebote, consulta el siguiente documento:

➡️ **Documentación del Sistema de Motor**

---

## 🔧 Solución de Problemas

Si encuentras problemas como el motor no se detiene, las fichas no se cuentan correctamente o la GUI no se actualiza, hemos preparado una guía específica con las causas más comunes y sus soluciones.

➡️ **Guía de Solución de Problemas**

---

## 📁 Estructura del Repositorio

```
expendedoraExperimental/
├── expendedora_core.py     # Lógica principal del motor y sensor.
├── expendedora_gui.py      # Interfaz gráfica para el operador.
├── shared_buffer.py        # Módulo para comunicación segura entre hilos.
├── main.py                 # Punto de entrada de la aplicación.
├── config.json             # Archivo de configuración de promociones y precios.
├── registro.json           # Registro de ventas y operaciones.
├── configSO/               # Scripts para configurar el SO (modo kiosk).
│   ├── crear_usuario_cajero.sh
│   └── restricciones_cajero.sh
└── Notas/                    # Documentación detallada del proyecto.
    ├── USUARIO_CAJERO_README.md
    ├── SISTEMA_MOTOR.md
    └── SOLUCION_PROBLEMAS.md
```

---
