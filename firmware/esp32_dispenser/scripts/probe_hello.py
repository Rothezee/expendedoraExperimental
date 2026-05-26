"""Prueba rápida HELLO en COM9 (o el puerto indicado)."""
import json
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM9"
BAUD = 115200

hello = json.dumps({"dir": "cmd", "type": "HELLO", "v": 1}, separators=(",", ":")) + "\n"

with serial.Serial(PORT, BAUD, timeout=0.5) as ser:
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.write(hello.encode("utf-8"))
    ser.flush()
    print(f"Enviado HELLO a {PORT}")
    deadline = time.time() + 2.0
    while time.time() < deadline:
        line = ser.readline().decode("utf-8", errors="replace").strip()
        if line:
            print(f"<- {line}")
