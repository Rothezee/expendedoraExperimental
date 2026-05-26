import unittest
from unittest.mock import Mock, patch

from services.network_manager_service import NetworkManagerService


class NetworkManagerServiceTest(unittest.TestCase):
    def test_parse_windows_wlan_block_connected(self):
        block = (
            "Name                   : Wi-Fi\n"
            "Description            : Intel(R) Wi-Fi 6\n"
            "State                  : connected\n"
            "SSID                   : MiRed\n"
            "Signal                 : 82%\n"
        )
        parsed = NetworkManagerService._parse_windows_wlan_block(block)
        self.assertEqual(parsed["active_connection"], "MiRed")
        self.assertEqual(parsed["active_device"], "Wi-Fi")
        self.assertEqual(parsed["signal_percent"], 82)

    def test_parse_windows_wlan_block_disconnected(self):
        block = (
            "Nombre                 : Wi-Fi\n"
            "Descripci\u00f3n           : Intel(R) Wi-Fi 6\n"
            "Estado                 : desconectado\n"
            "SSID                   : MiRed\n"
            "Se\u00f1al                : 50%\n"
        )
        parsed = NetworkManagerService._parse_windows_wlan_block(block)
        self.assertEqual(parsed["active_connection"], "")
        self.assertEqual(parsed["active_device"], "Wi-Fi")
        self.assertEqual(parsed["signal_percent"], 50)

    @patch("services.network_manager_service.subprocess.run")
    def test_list_wifi_networks_windows_parses_ssids(self, run_mock):
        run_mock.return_value = Mock(
            stdout=(
                "SSID 1 : Casa\n"
                "    Network type            : Infrastructure\n"
                "SSID 2 : HotspotPhone\n"
            )
        )
        ssids = NetworkManagerService._list_wifi_networks_windows()
        self.assertEqual(ssids, ["Casa", "HotspotPhone"])

    def test_parse_windows_connected_interfaces(self):
        text = (
            "Admin State    State          Type             Interface Name\n"
            "-------------------------------------------------------------------------\n"
            "Enabled        Connected      Dedicated        Ethernet\n"
            "Enabled        Disconnected   Dedicated        Wi-Fi\n"
            "Enabled        Connected      Dedicated        Ethernet 2\n"
        )
        parsed = NetworkManagerService._parse_windows_connected_interfaces(text)
        self.assertEqual(parsed, ["Ethernet", "Ethernet 2"])

    @patch("services.network_manager_service.subprocess.run")
    def test_windows_active_connection_falls_back_to_wired(self, run_mock):
        run_mock.side_effect = [
            Mock(stdout=""),  # netsh wlan show interfaces
            Mock(
                stdout=(
                    "Admin State    State          Type             Interface Name\n"
                    "-------------------------------------------------------------------------\n"
                    "Enabled        Connected      Dedicated        Ethernet\n"
                )
            ),  # netsh interface show interface
        ]
        parsed = NetworkManagerService._windows_active_connection()
        self.assertEqual(parsed["active_connection"], "Ethernet")
        self.assertEqual(parsed["active_device"], "Ethernet")


if __name__ == "__main__":
    unittest.main()
