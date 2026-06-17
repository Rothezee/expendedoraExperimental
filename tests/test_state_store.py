import json
import os
import tempfile
import unittest
from unittest.mock import patch

from expendedora.persistence.json import state_store
from expendedora.logic.services.counter_service import CounterService


class TestStateStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.state_path = os.path.join(self.base, "machine_state.json")
        self.config_path = os.path.join(self.base, "config.json")
        self.buffer_path = os.path.join(self.base, "buffer_state.json")
        self.registro_path = os.path.join(self.base, "registro.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_atomic_write_leaves_no_tmp(self):
        path = os.path.join(self.base, "test.json")
        state_store.atomic_write_json(path, {"a": 1})
        self.assertTrue(os.path.exists(path))
        self.assertEqual(len([name for name in os.listdir(self.base) if name.startswith("test.json.") and name.endswith(".tmp")]), 0)

    def test_atomic_write_retries_replace_on_permission_error(self):
        path = os.path.join(self.base, "retry.json")
        original_replace = state_store.os.replace
        calls = {"n": 0}

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("locked")
            return original_replace(src, dst)

        with patch("expendedora.persistence.json.state_store.os.replace", side_effect=flaky_replace):
            with patch("expendedora.persistence.json.state_store.time.sleep", return_value=None):
                state_store.atomic_write_json(path, {"ok": True})

        self.assertTrue(os.path.exists(path))
        self.assertGreaterEqual(calls["n"], 3)

    def test_load_snapshot_uses_bak_when_main_corrupt(self):
        good = state_store.build_snapshot(
            buffer={"fichas_restantes": 7},
            revision=1,
        )
        state_store.atomic_write_json(self.state_path, good)
        with open(self.state_path, "w", encoding="utf-8") as f:
            f.write("{not json")
        loaded = state_store.load_snapshot(self.state_path)
        self.assertIsNone(loaded)
        if os.path.exists(f"{self.state_path}.bak"):
            shutil_bak = state_store._safe_load_json(f"{self.state_path}.bak")
            self.assertIsNotNone(shutil_bak)

    def test_recover_picks_max_fichas_expendidas(self):
        state_store.atomic_write_json(
            self.buffer_path,
            {"fichas_expendidas": 50, "fichas_restantes": 2},
        )
        state_store.atomic_write_json(
            self.config_path,
            {
                "contadores": {
                    "fichas_expendidas": 100,
                    "fichas_restantes": 1,
                    "dinero_ingresado": 0,
                    "promo1_contador": 0,
                    "promo2_contador": 0,
                    "promo3_contador": 0,
                    "fichas_devolucion": 0,
                    "fichas_normales": 0,
                    "fichas_promocion": 0,
                    "fichas_cambio": 0,
                }
            },
        )
        snap = state_store.recover_state(
            config_path=self.config_path,
            buffer_path=self.buffer_path,
            registro_path=self.registro_path,
            state_path=self.state_path,
        )
        self.assertEqual(snap["contadores_global"]["fichas_expendidas"], 100)
        self.assertEqual(snap["buffer"]["fichas_expendidas"], 100)

    def test_recover_fichas_restantes_from_newer_timestamp(self):
        old_ts = "2020-01-01 10:00:00"
        new_ts = "2026-05-18 14:00:00"
        state_store.atomic_write_json(
            self.state_path,
            {
                "schema_version": 1,
                "revision": 1,
                "updated_at": old_ts,
                "buffer": {"fichas_restantes": 1, "fichas_expendidas": 0, "fichas_expendidas_sesion": 0, "cuenta": 0, "r_cuenta": 0},
                "contadores_global": {
                    "fichas_restantes": 1,
                    "fichas_expendidas": 0,
                    "dinero_ingresado": 0,
                    "promo1_contador": 0,
                    "promo2_contador": 0,
                    "promo3_contador": 0,
                    "fichas_devolucion": 0,
                    "fichas_normales": 0,
                    "fichas_promocion": 0,
                    "fichas_cambio": 0,
                },
                "contadores_parcial": CounterService.ensure_schema({}),
            },
        )
        state_store.atomic_write_json(
            self.config_path,
            {
                "updated_at": new_ts,
                "contadores_global": {
                    "fichas_restantes": 9,
                    "fichas_expendidas": 0,
                    "dinero_ingresado": 0,
                    "promo1_contador": 0,
                    "promo2_contador": 0,
                    "promo3_contador": 0,
                    "fichas_devolucion": 0,
                    "fichas_normales": 0,
                    "fichas_promocion": 0,
                    "fichas_cambio": 0,
                },
            },
        )
        snap = state_store.recover_state(
            config_path=self.config_path,
            buffer_path=self.buffer_path,
            registro_path=self.registro_path,
            state_path=self.state_path,
        )
        self.assertEqual(snap["contadores_global"]["fichas_restantes"], 1)
        self.assertEqual(snap["buffer"]["fichas_restantes"], 1)

    def test_recover_prefers_machine_buffer_over_newer_config(self):
        """config.json más nuevo no debe revivir fichas ya dispensadas."""
        old_ts = "2020-01-01 10:00:00"
        new_ts = "2026-05-18 14:00:00"
        state_store.atomic_write_json(
            self.state_path,
            {
                "schema_version": 1,
                "revision": 2,
                "updated_at": old_ts,
                "buffer": {
                    "fichas_restantes": 0,
                    "fichas_expendidas": 10,
                    "fichas_expendidas_sesion": 10,
                    "cuenta": 0,
                    "r_cuenta": 0,
                },
                "contadores_global": CounterService.ensure_schema({"fichas_expendidas": 10}),
                "contadores_parcial": CounterService.ensure_schema({}),
                "pending_lots": [],
            },
        )
        state_store.atomic_write_json(
            self.config_path,
            {
                "updated_at": new_ts,
                "contadores_global": {
                    "fichas_restantes": 9,
                    "fichas_expendidas": 0,
                    "dinero_ingresado": 0,
                    "promo1_contador": 0,
                    "promo2_contador": 0,
                    "promo3_contador": 0,
                    "fichas_devolucion": 0,
                    "fichas_normales": 0,
                    "fichas_promocion": 0,
                    "fichas_cambio": 0,
                },
            },
        )
        snap = state_store.recover_state(
            config_path=self.config_path,
            buffer_path=self.buffer_path,
            registro_path=self.registro_path,
            state_path=self.state_path,
        )
        self.assertEqual(snap["buffer"]["fichas_restantes"], 0)
        self.assertEqual(snap["contadores_global"]["fichas_restantes"], 0)
        self.assertEqual(snap.get("pending_lots"), [])

    def test_corrupt_machine_state_falls_back_to_config(self):
        with open(self.state_path, "w", encoding="utf-8") as f:
            f.write("broken")
        state_store.atomic_write_json(
            self.config_path,
            {
                "contadores_global": {
                    "fichas_expendidas": 42,
                    "fichas_restantes": 3,
                    "dinero_ingresado": 0,
                    "promo1_contador": 0,
                    "promo2_contador": 0,
                    "promo3_contador": 0,
                    "fichas_devolucion": 0,
                    "fichas_normales": 0,
                    "fichas_promocion": 0,
                    "fichas_cambio": 0,
                }
            },
        )
        snap = state_store.recover_state(
            config_path=self.config_path,
            buffer_path=self.buffer_path,
            registro_path=self.registro_path,
            state_path=self.state_path,
        )
        self.assertEqual(snap["contadores_global"]["fichas_expendidas"], 42)

    def test_save_snapshot_increments_revision(self):
        s1 = state_store.build_snapshot(revision=1)
        state_store.save_snapshot(s1, path=self.state_path)
        s2 = state_store.load_snapshot(self.state_path)
        self.assertIsNotNone(s2)
        rev1 = s2["revision"]
        state_store.save_snapshot(s2, path=self.state_path)
        s3 = state_store.load_snapshot(self.state_path)
        self.assertGreater(s3["revision"], rev1)

    def test_recover_does_not_override_explicit_reset_with_registro(self):
        state_store.atomic_write_json(
            self.config_path,
            {
                "contadores_global": {
                    "fichas_expendidas": 0,
                    "fichas_restantes": 0,
                    "dinero_ingresado": 0,
                    "promo1_contador": 0,
                    "promo2_contador": 0,
                    "promo3_contador": 0,
                    "fichas_devolucion": 0,
                    "fichas_normales": 0,
                    "fichas_promocion": 0,
                    "fichas_cambio": 0,
                }
            },
        )
        state_store.atomic_write_json(self.registro_path, {"fichas_expendidas": 25})
        snap = state_store.recover_state(
            config_path=self.config_path,
            buffer_path=self.buffer_path,
            registro_path=self.registro_path,
            state_path=self.state_path,
        )
        self.assertEqual(snap["contadores_global"]["fichas_expendidas"], 0)
        self.assertEqual(snap["buffer"]["fichas_expendidas"], 0)

    def test_recover_uses_registro_as_fallback_when_state_is_empty(self):
        state_store.atomic_write_json(self.registro_path, {"fichas_expendidas": 12})
        snap = state_store.recover_state(
            config_path=self.config_path,
            buffer_path=self.buffer_path,
            registro_path=self.registro_path,
            state_path=self.state_path,
        )
        self.assertEqual(snap["contadores_global"]["fichas_expendidas"], 12)
        self.assertEqual(snap["buffer"]["fichas_expendidas"], 12)


if __name__ == "__main__":
    unittest.main()
