"""Tests de salud de conexión serial."""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from expendedora.logic.hardware.serial_bridge import SerialBridge
from expendedora.logic.hardware.serial_client import SerialBackend
from expendedora.logic.services.machine_state import MachineState


class SerialHealthTest(unittest.TestCase):
    def _backend(self, *, connected=False, reader_alive=False):
        backend = SerialBackend.__new__(SerialBackend)
        backend._connected = connected
        backend._serial = object() if connected else None
        backend._on_serial_activity = None
        backend._last_serial_activity_ts = 0.0
        if reader_alive:
            thread = MagicMock(spec=threading.Thread)
            thread.is_alive.return_value = True
            backend._reader_thread = thread
        else:
            backend._reader_thread = None
        return backend

    def test_is_connected_false_without_reader_thread(self):
        self.assertFalse(self._backend(connected=True).is_connected())

    def test_is_connected_false_when_reader_dead(self):
        backend = self._backend(connected=True)
        thread = MagicMock(spec=threading.Thread)
        thread.is_alive.return_value = False
        backend._reader_thread = thread
        self.assertFalse(backend.is_connected())

    def test_is_connected_true_when_reader_alive(self):
        self.assertTrue(self._backend(connected=True, reader_alive=True).is_connected())

    def test_serial_activity_callback_updates_timestamp(self):
        backend = self._backend()
        seen = []

        backend.set_serial_activity_callback(lambda: seen.append(1))
        backend._notify_serial_activity()
        self.assertEqual(seen, [1])
        self.assertGreater(backend.last_serial_activity_ts(), 0.0)

    def test_configure_hopper_sends_single_config_frame(self):
        backend = SerialBackend.__new__(SerialBackend)
        backend._settings = {"debug_motor_sensor": False}
        sent = []

        def _send_raw(payload):
            sent.append(payload)
            return True

        backend._send_raw = _send_raw
        backend._wait_for_event = MagicMock(return_value=True)
        hopper = {"id": 1, "motor_pin": 10, "sensor_pin": 9}
        destrabe = {"enabled": True, "retroceso_s": 1.5}
        self.assertTrue(backend.configure_hopper(hopper, destrabe))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["type"], "CONFIG")
        self.assertEqual(sent[0]["hopper"], hopper)
        self.assertEqual(sent[0]["destrabe"], destrabe)

    def _bridge_with_backend(self, fichas=0):
        tolva = MagicMock()
        tolva.bloqueo_emergencia = False
        tolva._tolvas_lock = threading.Lock()
        tolva._tolvas_trabadas = set()
        tolva._tolva_seleccionada_idx = 0
        tolva._tolvas = [{"id": 1, "motor_pin": 10, "motor_pin_rev": 12, "sensor_pin": 9}]
        ms = MachineState()
        ms.set_fichas_restantes(fichas, immediate=False)
        bridge = SerialBridge(ms, tolva)
        backend = MagicMock()
        backend.is_connected.return_value = True
        backend.set_serial_activity_callback = MagicMock()
        bridge._backend = backend
        bridge._last_rx_ts = time.time() - 20.0
        bridge._last_cmd_ts = time.time()
        return bridge, backend

    def test_watchdog_skipped_when_rx_recent(self):
        bridge, backend = self._bridge_with_backend()
        bridge._touch_rx()
        with patch.object(bridge, "force_reconnect") as forced:
            bridge._check_connection_health()
        backend.ping_wait_pong.assert_not_called()
        forced.assert_not_called()

    def test_watchdog_ping_ok_avoids_reconnect(self):
        bridge, backend = self._bridge_with_backend(fichas=1)
        backend.ping_wait_pong.return_value = True
        with patch.object(bridge, "force_reconnect") as forced:
            bridge._check_connection_health()
        backend.ping_wait_pong.assert_called_once()
        forced.assert_not_called()
        self.assertGreater(bridge._last_rx_ts, time.time() - 1.0)

    def test_watchdog_ping_fail_forces_reconnect(self):
        bridge, backend = self._bridge_with_backend(fichas=1)
        backend.ping_wait_pong.return_value = False
        with patch.object(bridge, "force_reconnect") as forced:
            bridge._check_connection_health()
        backend.ping_wait_pong.assert_called_once()
        forced.assert_called_once()

    def test_wire_backend_callbacks_registers_touch_rx(self):
        bridge, backend = self._bridge_with_backend()
        captured = {}

        def _capture(cb):
            captured["cb"] = cb

        backend.set_serial_activity_callback = _capture
        bridge._wire_backend_callbacks()
        self.assertIsNotNone(captured.get("cb"))
        captured["cb"]()
        self.assertGreater(bridge._last_rx_ts, 0.0)


if __name__ == "__main__":
    unittest.main()
