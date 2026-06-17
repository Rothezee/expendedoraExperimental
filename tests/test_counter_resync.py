"""Tests de re-sincronización PC↔MCU (PC autoritativo)."""

import unittest
from unittest.mock import MagicMock

from expendedora.logic.hardware.serial_bridge import SerialBridge
from expendedora.logic.services.machine_state import MachineState


class CounterResyncTest(unittest.TestCase):
    def _bridge(self, fichas=70, *, connected=True):
        tolva = MagicMock()
        tolva.bloqueo_emergencia = False
        tolva._tolvas_lock = __import__("threading").Lock()
        tolva._tolvas_trabadas = set()
        tolva._destrabe_request_lock = __import__("threading").Lock()
        tolva._destrabe_requested = {"tolva_id": None, "ts": 0.0}
        tolva._tolva_seleccionada_idx = 0
        tolva._tolvas = [{"id": 1, "motor_pin": 10, "motor_pin_rev": 12, "sensor_pin": 9}]
        ms = MachineState()
        ms.set_fichas_restantes(fichas, immediate=False)
        bridge = SerialBridge(ms, tolva)
        backend = MagicMock()
        backend.is_connected.return_value = connected
        backend.set_target.return_value = True
        bridge._backend = backend
        bridge._config_applied = True
        return bridge, ms, backend

    def test_token_decrements_pc_by_one_not_mcu_remaining(self):
        bridge, ms, backend = self._bridge(70)
        bridge._handle_event({"type": "TOKEN", "hopper_id": 1, "remaining": 0})
        self.assertEqual(ms.get_fichas_restantes(), 69)
        backend.set_target.assert_called_with(69)

    def test_sync_desfase_triggers_set_target_from_pc(self):
        bridge, ms, backend = self._bridge(50)
        bridge._last_sent_target = 50
        bridge._handle_event({"type": "SYNC", "hopper_id": 1, "remaining": 0})
        backend.set_target.assert_called_with(50)

    def test_run_done_does_not_zero_pc_when_pending(self):
        bridge, ms, backend = self._bridge(30)
        bridge._handle_event({"type": "RUN_DONE", "hopper_id": 1, "remaining": 0})
        self.assertEqual(ms.get_fichas_restantes(), 30)
        backend.set_target.assert_called_with(30)

    def test_periodic_retry_when_mcu_not_confirmed(self):
        bridge, ms, backend = self._bridge(70)
        bridge._last_sent_target = 70
        bridge._mcu_target_confirmed = False
        bridge._last_target_push_ts = 0.0
        bridge._last_resync_ts = 0.0
        bridge._maybe_periodic_resync()
        backend.set_target.assert_called_with(70)

    def test_ensure_pending_arms_dispense_after_recovery(self):
        bridge, ms, backend = self._bridge(40)
        bridge._dispense_armed = False
        bridge._ensure_pending_dispense_armed()
        self.assertTrue(bridge._dispense_armed)
        self.assertFalse(bridge._mcu_target_confirmed)

    def test_recover_pending_dispense_retries_set_target(self):
        bridge, ms, backend = self._bridge(25)
        ok = bridge._recover_pending_dispense(reason="test")
        self.assertTrue(ok)
        self.assertGreaterEqual(backend.set_target.call_count, 1)
        backend.set_target.assert_called_with(25)

    def test_reconcile_after_config_resets_mcu(self):
        bridge, ms, backend = self._bridge(70)
        bridge._last_sent_target = 70
        bridge._last_mcu_remaining = 0
        bridge._reconcile_with_mcu(0, source="test")
        backend.set_target.assert_called_with(70)
