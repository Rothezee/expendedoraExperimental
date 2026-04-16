import unittest
from unittest.mock import patch

from infra.telemetry_client import TelemetryClient


class _FakeConfigRepo:
    def load(self):
        return {
            "api": {
                "base_urls": ["http://127.0.0.1", "https://app.maquinasbonus.com"],
                "endpoint_receptor": "AdministrationPanel/src/devices/api_receptor.php",
                "endpoint_receptor_local": "AdministrationPanel/src/devices/api_receptor.php",
                "endpoint_receptor_cloud": "src/devices/api_receptor.php",
                "endpoint_receptor_cloud_fallback": "AdministrationPanel/src/devices/api_receptor.php",
                "timeout_s": 7,
                "headers": {"X-Api-Key": "secret-token"},
            },
            "admin": {"dni_admin": "123"},
            "maquina": {"codigo_hardware": "EXP_1", "tipo_maquina": 1},
        }

class _FakeConfigRepoNoFallback:
    def load(self):
        return {
            "api": {
                "base_urls": ["http://127.0.0.1", "https://app.maquinasbonus.com"],
                "endpoint_receptor": "AdministrationPanel/src/devices/api_receptor.php",
                "endpoint_receptor_local": "AdministrationPanel/src/devices/api_receptor.php",
                "endpoint_receptor_cloud": "src/devices/api_receptor.php",
                "endpoint_receptor_cloud_fallback": "",
                "timeout_s": 7,
                "headers": {},
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
        self.assertEqual(body["fichas"], 5)
        self.assertEqual(body["dinero"], 1200.5)
        self.assertNotIn("payload", body)

    @patch("infra.telemetry_client.requests.post")
    def test_post_body_sends_to_all_urls(self, post_mock):
        post_mock.return_value = unittest.mock.Mock(status_code=200, text="OK", headers={})
        self.client.post_body({"action": 1}, "heartbeat")
        self.assertEqual(post_mock.call_count, 2)
        called_urls = [args[0] for args, _kwargs in post_mock.call_args_list]
        self.assertIn(
            "http://127.0.0.1/AdministrationPanel/src/devices/api_receptor.php",
            called_urls,
        )
        self.assertIn(
            "https://app.maquinasbonus.com/src/devices/api_receptor.php",
            called_urls,
        )
        for _args, kwargs in post_mock.call_args_list:
            headers = kwargs.get("headers", {})
            self.assertEqual(headers.get("X-Api-Key"), "secret-token")
            self.assertEqual(headers.get("User-Agent"), "ExpendedoraTelemetry/1.0")

    @patch("infra.telemetry_client.requests.post")
    def test_post_body_retries_cloud_with_fallback_on_403(self, post_mock):
        local_ok = unittest.mock.Mock(status_code=200, text="OK", headers={})
        cloud_forbidden = unittest.mock.Mock(
            status_code=403,
            text="forbidden",
            headers={"Server": "nginx"},
        )
        cloud_fallback_ok = unittest.mock.Mock(status_code=200, text="OK", headers={})
        post_mock.side_effect = [local_ok, cloud_forbidden, cloud_fallback_ok]

        self.client.post_body({"action": 2}, "telemetria")

        self.assertEqual(post_mock.call_count, 3)
        called_urls = [args[0] for args, _kwargs in post_mock.call_args_list]
        self.assertEqual(
            called_urls,
            [
                "http://127.0.0.1/AdministrationPanel/src/devices/api_receptor.php",
                "https://app.maquinasbonus.com/src/devices/api_receptor.php",
                "https://app.maquinasbonus.com/AdministrationPanel/src/devices/api_receptor.php",
            ],
        )

    @patch("infra.telemetry_client.requests.post")
    def test_post_body_does_not_retry_when_cloud_fallback_disabled(self, post_mock):
        client = TelemetryClient(_FakeConfigRepoNoFallback())
        local_ok = unittest.mock.Mock(status_code=200, text="OK", headers={})
        cloud_forbidden = unittest.mock.Mock(status_code=403, text="forbidden", headers={})
        post_mock.side_effect = [local_ok, cloud_forbidden]

        client.post_body({"action": 1}, "heartbeat")

        self.assertEqual(post_mock.call_count, 2)
        called_urls = [args[0] for args, _kwargs in post_mock.call_args_list]
        self.assertEqual(
            called_urls,
            [
                "http://127.0.0.1/AdministrationPanel/src/devices/api_receptor.php",
                "https://app.maquinasbonus.com/src/devices/api_receptor.php",
            ],
        )


if __name__ == "__main__":
    unittest.main()

