import unittest
from unittest.mock import MagicMock, patch

from infra.auth_repository_mysql import AuthRepositoryMySQL
from infra.config_repository import ConfigRepository


class _FakeConfigRepo(ConfigRepository):
    def __init__(self):
        pass

    def load(self):
        return {
            "mysql": {
                "host": "localhost",
                "port": 3306,
                "user": "root",
                "password": "",
                "database": "sistemadeadministracion",
            },
            "admin": {"dni_admin": "00000000"},
        }


class AuthRepositoryTest(unittest.TestCase):
    @patch("infra.auth_repository_mysql.mysql.connector.connect")
    def test_authenticate_cashier_returns_row(self, connect_mock):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1, "cajero", 7)
        conn = MagicMock()
        conn.cursor.return_value = cursor
        connect_mock.return_value = conn

        repo = AuthRepositoryMySQL(_FakeConfigRepo())
        row = repo.authenticate_cashier("cajero", "1234")
        self.assertEqual(row, (1, "cajero", 7))
        self.assertTrue(cursor.execute.called)

    @patch("infra.auth_repository_mysql.mysql.connector.connect")
    def test_create_cashier_require_remote_raises_when_unreachable(self, connect_mock):
        connect_mock.side_effect = RuntimeError("connect failed")
        repo = AuthRepositoryMySQL(_FakeConfigRepo())
        with self.assertRaises(ConnectionError):
            repo.create_cashier("cajero", "1234", require_remote=True)


if __name__ == "__main__":
    unittest.main()

