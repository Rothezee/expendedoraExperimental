import mysql.connector

from infra.config_repository import ConfigRepository


class AuthRepositoryMySQL:
    def __init__(self, config_repository: ConfigRepository):
        self.config_repository = config_repository

    def _connect(self):
        config = self.config_repository.load()
        mysql_cfg = config.get("mysql", {})
        return mysql.connector.connect(
            host=mysql_cfg.get("host", "localhost"),
            port=mysql_cfg.get("port", 3306),
            user=mysql_cfg.get("user", "root"),
            password=mysql_cfg.get("password", ""),
            database=mysql_cfg.get("database", "sistemadeadministracion"),
        )

    def _get_dni_admin(self) -> str | None:
        config = self.config_repository.load()
        dni = str(config.get("admin", {}).get("dni_admin", "")).strip()
        return dni or None

    def check_schema(self) -> None:
        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM usuarios_admin LIMIT 1")
            cursor.fetchone()
            cursor.execute("SELECT 1 FROM cajeros LIMIT 1")
            cursor.fetchone()
        finally:
            conn.close()

    def _admin_id_by_dni(self, cursor, dni_admin: str | None) -> int | None:
        if not dni_admin:
            return None
        cursor.execute("SELECT id_admin FROM usuarios_admin WHERE dni = %s LIMIT 1", (dni_admin,))
        row = cursor.fetchone()
        return row[0] if row else None

    def create_cashier(self, username: str, pin: str) -> bool:
        conn = self._connect()
        cursor = conn.cursor()
        try:
            admin_id = self._admin_id_by_dni(cursor, self._get_dni_admin())
            if not admin_id:
                return False
            cursor.execute(
                "SELECT id_cajero FROM cajeros WHERE id_admin = %s AND usuario_cajero = %s LIMIT 1",
                (admin_id, username),
            )
            if cursor.fetchone():
                return False
            cursor.execute(
                """
                INSERT INTO cajeros (id_admin, usuario_cajero, pin_acceso, estado)
                VALUES (%s, %s, %s, 1)
                """,
                (admin_id, username, pin),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def authenticate_cashier(self, username: str, pin: str):
        conn = self._connect()
        cursor = conn.cursor()
        try:
            dni_admin = self._get_dni_admin()
            if dni_admin:
                cursor.execute(
                    """
                    SELECT c.id_cajero, c.usuario_cajero, c.id_admin
                    FROM cajeros c
                    INNER JOIN usuarios_admin a ON a.id_admin = c.id_admin
                    WHERE c.usuario_cajero = %s
                      AND c.pin_acceso = %s
                      AND c.estado = 1
                      AND a.dni = %s
                    LIMIT 1
                    """,
                    (username, pin, dni_admin),
                )
            else:
                cursor.execute(
                    """
                    SELECT c.id_cajero, c.usuario_cajero, c.id_admin
                    FROM cajeros c
                    WHERE c.usuario_cajero = %s
                      AND c.pin_acceso = %s
                      AND c.estado = 1
                    LIMIT 1
                    """,
                    (username, pin),
                )
            return cursor.fetchone()
        finally:
            conn.close()

