import unittest
from unittest.mock import Mock, patch

from infra.report_repository_mysql import ReportRepositoryMySQL
from infra.config_repository import ConfigRepository


class ReportRepositoryMySQLTest(unittest.TestCase):
    @patch("infra.report_repository_mysql.mysql.connector.connect")
    def test_unresolved_device_falls_back_to_unfiltered_query(self, connect_mock):
        config_repo = Mock(spec=ConfigRepository)
        config_repo.iter_mysql_targets.return_value = [
            {"host": "localhost", "port": 3306, "database": "db", "user": "u", "password": "p"}
        ]
        repo = ReportRepositoryMySQL(config_repo)

        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value = cursor
        connect_mock.return_value = conn

        # SHOW COLUMNS, resolve_device lookup, SELECT
        cursor.fetchall.side_effect = [
            [("id_cierre",), ("id_dispositivo",), ("dinero",)],
            [{"id_cierre": 10, "id_dispositivo": 1, "dinero": 50.0}],
        ]
        cursor.fetchone.return_value = None  # _resolve_device_id -> no mapeo

        rows = repo.fetch_daily_closures(limit=5, device_id="EXPENDEDORA_2")
        self.assertEqual(len(rows), 1)

        executed_sql = [call.args[0] for call in cursor.execute.call_args_list]
        select_sql = [sql for sql in executed_sql if str(sql).strip().upper().startswith("SELECT")][-1]
        self.assertNotIn("WHERE id_dispositivo = %s", select_sql)


if __name__ == "__main__":
    unittest.main()
