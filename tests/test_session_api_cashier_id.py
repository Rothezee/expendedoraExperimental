"""Tests de alineación id_cajero local vs remoto en subcierres."""

import unittest
from unittest.mock import MagicMock

from expendedora.persistence.remote.session_api_repository import SessionApiRepository


class SessionApiCashierIdTest(unittest.TestCase):
    def _repo(self, local_id=3, remote_id=99):
        auth = MagicMock()
        auth.resolve_cashier_id.side_effect = lambda username, production_only=False: (
            remote_id if production_only else local_id
        )
        return SessionApiRepository(MagicMock(), auth)

    def test_cloud_replaces_local_id_with_remote(self):
        repo = self._repo(local_id=3, remote_id=99)
        payload = {
            "usuario_cajero": "maria",
            "id_cajero": 3,
            "dinero": 100,
        }
        adapted = repo._adapt_payload_for_scope(payload, "cloud")
        self.assertEqual(adapted["id_cajero"], 99)
        self.assertEqual(adapted["usuario_cajero"], "maria")

    def test_cloud_without_remote_id_omits_numeric_id(self):
        auth = MagicMock()
        auth.resolve_cashier_id.return_value = None
        repo = SessionApiRepository(MagicMock(), auth)
        payload = {"usuario_cajero": "maria", "id_cajero": 3}
        adapted = repo._adapt_payload_for_scope(payload, "cloud")
        self.assertNotIn("id_cajero", adapted)
        self.assertEqual(adapted["usuario_cajero"], "maria")

    def test_local_uses_local_resolver(self):
        repo = self._repo(local_id=7, remote_id=99)
        payload = {"usuario_cajero": "maria", "id_cajero": 3}
        adapted = repo._adapt_payload_for_scope(payload, "local")
        self.assertEqual(adapted["id_cajero"], 7)

    def test_daily_close_payload_not_modified(self):
        repo = self._repo()
        payload = {"fichas_totales": 10, "dinero": 50, "tipo_evento": "cierre"}
        adapted = repo._adapt_payload_for_scope(payload, "cloud")
        self.assertEqual(adapted, payload)
