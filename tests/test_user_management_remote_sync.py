import unittest
from unittest.mock import Mock, patch

from User_management import database as user_db
from infra.auth_repository_mysql import AuthRepositoryMySQL


class UserManagementRemoteSyncTest(unittest.TestCase):
    def test_sync_pending_connection_error_keeps_remaining_queue(self):
        pending = [
            {"username": "u1", "pin": "1111"},
            {"username": "u2", "pin": "2222"},
        ]
        saved = {}

        with (
            patch.object(user_db, "_load_pending_sync", return_value=pending),
            patch.object(user_db, "_save_pending_sync", side_effect=lambda items: saved.setdefault("items", items)),
            patch.object(
                user_db._auth_repo,
                "create_cashier",
                side_effect=ConnectionError("remote down"),
            ),
        ):
            user_db._sync_pending_cashiers()

        self.assertIn("items", saved)
        self.assertEqual(saved["items"], pending)

    def test_create_cashier_uses_fallback_admin_if_dni_not_found(self):
        config_repo = Mock()
        repo = AuthRepositoryMySQL(config_repo)
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = [
            None,    # _admin_id_by_dni
            (42,),   # _admin_id_fallback
            None,    # usuario no existe
        ]

        with (
            patch.object(repo, "_connect", return_value=conn),
            patch.object(repo, "_get_dni_admin", return_value="00000000"),
        ):
            created = repo.create_cashier("cajero_test", "1234", require_remote=True)

        self.assertTrue(created)
        conn.commit.assert_called_once()
        cursor.execute.assert_any_call(
            """
                INSERT INTO cajeros (id_admin, usuario_cajero, pin_acceso, estado)
                VALUES (%s, %s, %s, 1)
                """,
            (42, "cajero_test", "1234"),
        )

    def test_create_cashier_remote_without_admin_raises_runtime_error(self):
        config_repo = Mock()
        repo = AuthRepositoryMySQL(config_repo)
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = [
            None,  # _admin_id_by_dni
            None,  # _admin_id_fallback
        ]

        with (
            patch.object(repo, "_connect", return_value=conn),
            patch.object(repo, "_get_dni_admin", return_value="00000000"),
        ):
            with self.assertRaises(RuntimeError):
                repo.create_cashier("cajero_test", "1234", require_remote=True)


if __name__ == "__main__":
    unittest.main()
