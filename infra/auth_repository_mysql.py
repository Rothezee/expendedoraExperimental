import mysql.connector

from infra.config_repository import ConfigRepository


class AuthRepositoryMySQL:
    def __init__(self, config_repository: ConfigRepository):
        self.config_repository = config_repository

    def _get_local_target(self):
        config = self.config_repository.load()
        mysql_cfg = config.get("mysql", {})
        if not isinstance(mysql_cfg, dict):
            mysql_cfg = {}
        local_cfg = mysql_cfg.get("local", {})
        if not isinstance(local_cfg, dict):
            local_cfg = {}
        return {
            "host": local_cfg.get("host", "localhost"),
            "port": local_cfg.get("port", 3306),
            "user": local_cfg.get("user", "root"),
            "password": local_cfg.get("password", ""),
            "database": local_cfg.get("database", "sistemadeadministracion"),
        }

    def _connect_local_only(self):
        target = self._get_local_target()
        return mysql.connector.connect(
            host=target.get("host", "localhost"),
            port=target.get("port", 3306),
            user=target.get("user", "root"),
            password=target.get("password", ""),
            database=target.get("database", "sistemadeadministracion"),
        )

    def _get_mysql_targets(self, only_production: bool = False):
        config = self.config_repository.load()
        mysql_cfg = config.get("mysql", {})
        if not isinstance(mysql_cfg, dict):
            mysql_cfg = {}

        active = str(mysql_cfg.get("active", "local")).lower()
        fallback = bool(mysql_cfg.get("fallback_to_secondary", True))
        local_cfg = mysql_cfg.get("local", {})
        prod_cfg = mysql_cfg.get("production", {})
        if not isinstance(local_cfg, dict):
            local_cfg = {}
        if not isinstance(prod_cfg, dict):
            prod_cfg = {}

        # Compatibilidad con formato viejo plano
        if any(key in mysql_cfg for key in ("host", "port", "user", "password", "database")):
            legacy = {
                "host": mysql_cfg.get("host", "localhost"),
                "port": mysql_cfg.get("port", 3306),
                "user": mysql_cfg.get("user", "root"),
                "password": mysql_cfg.get("password", ""),
                "database": mysql_cfg.get("database", "sistemadeadministracion"),
            }
            return [legacy]

        local_target = {
            "host": local_cfg.get("host", "localhost"),
            "port": local_cfg.get("port", 3306),
            "user": local_cfg.get("user", "root"),
            "password": local_cfg.get("password", ""),
            "database": local_cfg.get("database", "sistemadeadministracion"),
        }
        prod_target = {
            "host": prod_cfg.get("host", "localhost"),
            "port": prod_cfg.get("port", 3306),
            "user": prod_cfg.get("user", "root"),
            "password": prod_cfg.get("password", ""),
            "database": prod_cfg.get("database", "sistemadeadministracion"),
        }

        if only_production:
            return [prod_target]
        if active == "production":
            return [prod_target, local_target] if fallback else [prod_target]
        return [local_target, prod_target] if fallback else [local_target]

    def _connect(self, only_production: bool = False):
        last_exc = None
        for target in self._get_mysql_targets(only_production=only_production):
            try:
                return mysql.connector.connect(
                    host=target.get("host", "localhost"),
                    port=target.get("port", 3306),
                    user=target.get("user", "root"),
                    password=target.get("password", ""),
                    database=target.get("database", "sistemadeadministracion"),
                )
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
        raise RuntimeError("No MySQL targets configured")

    def _get_dni_admin(self) -> str | None:
        config = self.config_repository.load()
        dni = str(config.get("admin", {}).get("dni_admin", "")).strip()
        return dni or None

    def check_schema(self) -> None:
        local_exc = None
        try:
            # En arranque preferimos LOCAL para no depender del remoto.
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

