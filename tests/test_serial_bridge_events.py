"""Tests de eventos del puente serial."""

import unittest
from unittest.mock import MagicMock, patch

from expendedora.logic.hardware.serial_bridge import SerialBridge
from expendedora.logic.services.machine_state import MachineState


class SerialBridgeEventsTest(unittest.TestCase):
    def _bridge(self, fichas=3):
        tolva = MagicMock()
        tolva.bloqueo_emergencia = False
        tolva._tolvas_lock = __import__("threading").Lock()
        tolva._tolvas_trabadas = set()
        ms = MachineState()
        ms.set_fichas_restantes(fichas, immediate=False)
        bridge = SerialBridge(ms, tolva)
        bridge._backend = None
        return bridge, ms, tolva

    def test_token_with_mcu_delta(self):
        bridge, ms, _ = self._bridge(3)
        backend = MagicMock()
        backend.is_connected.return_value = True
        backend.set_target.return_value = True
        bridge._backend = backend
        bridge._config_applied = True
        bridge._handle_event({"type": "TOKEN", "hopper_id": 1, "remaining": 1})
        # PC autoritativo: 1 TOKEN = -1 ficha; MCU desfasado dispara re-sync
        self.assertEqual(ms.get_fichas_restantes(), 2)
        backend.set_target.assert_called_with(2)

    def test_jam_sets_emergency_and_unjam_clears(self):
        bridge, ms, tolva = self._bridge(2)
        bridge._handle_event({"type": "JAM", "hopper_id": 1, "remaining": 2})
        self.assertTrue(tolva.bloqueo_emergencia)
        bridge._handle_event({"type": "UNJAM_DONE", "hopper_id": 1})
        self.assertFalse(tolva.bloqueo_emergencia)

    def test_telemetry_callback_once_per_session_batch(self):
        bridge, ms, _ = self._bridge(0)
        ms._runtime.set("fichas_expendidas_sesion", 5)
        llamadas = []
        bridge._on_telemetry_done = lambda: llamadas.append(1)

        def _thread_sync(target, daemon=True):
            class _SyncThread:
                def start(self):
                    target()

            return _SyncThread()

        with patch("expendedora.logic.hardware.serial_bridge.threading.Thread", side_effect=_thread_sync):
            bridge._send_sale_report_if_done()
            bridge._send_sale_report_if_done()
        self.assertEqual(len(llamadas), 1)
