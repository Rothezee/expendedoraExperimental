"""Escenarios de ayuda rápida (el manual vive en docs/manual_usuario.md)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpScenario:
    label: str
    action: str
    summary: str


HELP_SCENARIOS: list[HelpScenario] = [
    HelpScenario(
        label="¿Las fichas salen pero no se cuentan?",
        action="help_fichas_no_cuentan",
        summary="Reinicia Arduino y permite reintentar la venta pendiente.",
    ),
    HelpScenario(
        label="¿Motor trabado?",
        action="help_motor_trabado",
        summary="Destraba con TEST_DISPENSE y verifica ficha de prueba (hasta ~18 s).",
    ),
    HelpScenario(
        label="¿Arduino sin conexión?",
        action="help_arduino_sin_conexion",
        summary="Intenta reconectar el puerto serial.",
    ),
    HelpScenario(
        label="¿Fichas pendientes que no salen?",
        action="help_pendientes_atascadas",
        summary="Reconecta Arduino o vacía buffer si la venta quedó mal.",
    ),
    HelpScenario(
        label="¿Ventana trabada / sin responder?",
        action="help_reiniciar_app",
        summary="Cierra sesión o reinicia la app (en kiosco puede reiniciar el proceso).",
    ),
]
