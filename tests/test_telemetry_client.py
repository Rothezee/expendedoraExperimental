import unittest
from unittest.mock import patch

from infra.telemetry_client import TelemetryClient


class _FakeConfigRepo:
    def load(self):
        return {
            "api": {
                "base_urls": ["http://127.0.0.1", "https://example.com"],
                "endpoint_receptor": "AdministrationPanel/src/devices/api_receptor.php",
                "timeout_s": 7,
            },
            "admin": {"dni_admin": "123"},
            "maquina": {"codigo_hardware": "EXP_1", "tipo_maquina": 1},
        }


class TelemetryClientTest(unittest.TestCase):
    def setUp(self):
        self.client = TelemetryClient(_FakeConfigRepo())

    def test_build_heartbeat_body(self):
        cfg = _FakeConfigRepo().load()
        body = self.client.build_heartbeat_body(cfg)
        self.assertEqual(body["action"], 1)
        self.assertEqual(body["codigo_hardware"], "EXP_1")
        self.assertNotIn("payload", body)

    def test_build_telemetry_body(self):
        cfg = _FakeConfigRepo().load()
        body = self.client.build_telemetry_body(cfg, fichas=5, dinero=1200.5)
        self.assertEqual(body["action"], 2)
        self.assertEqual(body["payload"]["fichas"], 5)
        self.assertEqual(body["payload"]["dinero"], 1200.5)

    @patch("infra.telemetry_client.requests.post")
    def test_post_body_sends_to_all_urls(self, post_mock):
        self.client.post_body({"action": 1}, "heartbeat")
        self.assertEqual(post_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()

