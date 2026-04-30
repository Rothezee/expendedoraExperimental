import unittest

import mysql.connector

from infra.db_exception_message import format_db_exception


class FormatDbExceptionTest(unittest.TestCase):
    def test_mysql_operational_known_message(self):
        exc = mysql.connector.OperationalError("Access denied for user X", 1045)
        out = format_db_exception(exc)
        self.assertIn("1045", out)
        self.assertIn("Access denied", out)

    def test_plain_str_zero_walks_context(self):
        class Inner(Exception):
            pass

        class Outer(Exception):
            def __str__(self):
                return "0"

        e = Outer()
        e.__cause__ = Inner("Sin ruta al host MySQL.")
        self.assertIn("Sin ruta", format_db_exception(e))

    def test_empty_runtimeerror_mentions_config(self):
        exc = RuntimeError()
        self.assertFalse(str(exc).strip())
        out = format_db_exception(exc)
        self.assertIn("config.json", out)


if __name__ == "__main__":
    unittest.main()
