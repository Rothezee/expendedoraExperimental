import mysql.connector

from infra.config_repository import ConfigRepository


class AuthRepositoryMySQL:
    def __init__(self, config_repository: ConfigRepository):
        self.config_repository = config_repository

    def _connect_local_only(self):
        cfg = self.config_repository.load()
        mysql_cfg = cfg.get("mysql", {})
        if not isinstance(mysql_cfg, dict):
            mysql_cfg = {}
        legacy_keys = ("host", "port", "user", "password", "database")
        if any(k in mysql_cfg for k in legacy_keys):
            target = self.config_repository.mysql_connection_params(mysql_cfg)
        else:
            local_raw = mysql_cfg.get("local", {})
            if not isinstance(local_raw, dict):
                local_raw = {}
            target = self.config_repository.mysql_connection_params(local_raw)
        return mysql.connector.connect(**target)

    def _connect(self, only_production: bool = False):
        last_exc = None
        for target in self.config_repository.iter_mysql_targets(production_only=only_production):
            try:
                return mysql.connector.connect(**target)
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
        raise RuntimeError("No MySQL targets configured")

    def _get_dni_admin(self) -> str | None:
        config = self.config_repository.load()
        admin = config.get("admin", {})
        if not isinstance(admin, dict):
            admin = {}
        dni = str(admin.get("dni_admin", "")).strip()
        return dni or None

    def check_schema(self) -> None:
        local_exc = None
        try:
            conn = self._connect_local_only()
        except Exception as exc:
            local_exc = exc
            conn = None

        if conn is None:
            try:
                conn = self._connect()
            except Exception as exc:
                raise RuntimeError(
                    "No se pudo conectar a MySQL local ni remoto para validar el esquema. "
                    f"Local error: {type(local_exc).__name__}: {local_exc}. "
                    f"Remote/active error: {type(exc).__name__}: {exc}."
                ) from exc

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

    def create_cashier(self, username: str, pin: str, require_remote: bool = False) -> bool:
        try:
            conn = self._connect(only_production=require_remote)
        except Exception as exc:
            if require_remote:
                raise ConnectionError(
                    "No se pudo conectar a la base de datos remota. "
                    "Verifica conexión a internet/WiFi y credenciales de producción."
                ) from exc
            raise
        cursor = conn.cursor()
        try:
            admin_id = self._admin_id_by_dni(cursor, self._get_dni_admin())
            if not admin_id:
                if require_remote:
                    raise RuntimeError(
                        "No se encontró el administrador remoto para el DNI configurado. "
                        "No se puede registrar el cajero sin sincronizar el panel."
                    )
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
