from __future__ import annotations

import mysql.connector

from infra.config_repository import ConfigRepository


class ReportRepositoryMySQL:
    def __init__(self, config_repository: ConfigRepository):
        self.config_repository = config_repository

    def _get_mysql_targets(self):
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
        if active == "production":
            return [prod_target, local_target] if fallback else [prod_target]
        return [local_target, prod_target] if fallback else [local_target]

    def _connect(self):
        last_exc = None
        targets = list(self._get_mysql_targets())
        # En la expendedora (kiosk) preferimos leer desde la BD local.
        # Si "active=production" está configurado pero el remoto falla,
        # igual queremos que la UI de reportes funcione.
        def _is_local(t: dict) -> bool:
            host = str(t.get("host", "") or "").strip().lower()
            return host in ("localhost", "127.0.0.1", "::1")

        targets.sort(key=lambda t: 0 if _is_local(t) else 1)

        for target in targets:
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
        if last_exc:
            raise last_exc
        raise RuntimeError("No MySQL targets configured")

    @staticmethod
    def _safe_limit(limit: int) -> int:
        try:
            parsed = int(limit)
        except (TypeError, ValueError):
            parsed = 50
        return max(1, min(parsed, 500))

    @staticmethod
    def _available_columns(cursor, table: str) -> set[str]:
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        return {str(row[0]) for row in cursor.fetchall()}

    def _select_rows(self, table: str, preferred_columns: list[str], order_column: str, limit: int, device_id: str = ""):
        conn = self._connect()
        cursor = conn.cursor(dictionary=True)
        try:
            available = self._available_columns(cursor, table)
            selected_columns = [col for col in preferred_columns if col in available]
            if not selected_columns:
                raise RuntimeError(f"No hay columnas esperadas en {table}.")
            sql = f"SELECT {', '.join(selected_columns)} FROM {table}"
            params = []
            if device_id and "id_dispositivo" in available:
                sql += " WHERE id_dispositivo = %s"
                params.append(device_id)
            sort_column = order_column if order_column in available else selected_columns[0]
            sql += f" ORDER BY {sort_column} DESC LIMIT %s"
            params.append(self._safe_limit(limit))
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
        finally:
            conn.close()

    def fetch_daily_closures(self, limit: int = 50, device_id: str = ""):
        columns = [
            "id_cierre",
            "id_dispositivo",
            "fichas_totales",
            "dinero",
            "p1",
            "p2",
            "p3",
            "fichas_promo",
            "fecha_apertura",
            "tipo_evento",
        ]
        return self._select_rows(
            table="cierres_diarios",
            preferred_columns=columns,
            order_column="id_cierre",
            limit=limit,
            device_id=device_id,
        )

    def fetch_partial_closures(self, limit: int = 50, device_id: str = ""):
        columns = [
            "id_cierre_parcial",
            "id_dispositivo",
            "id_cajero",
            "fichas_totales",
            "dinero",
            "p1",
            "p2",
            "p3",
            "fichas_promo",
            "fichas_devolucion",
            "fichas_cambio",
            "fecha_apertura_turno",
        ]
        return self._select_rows(
            table="cierres_parciales",
            preferred_columns=columns,
            order_column="id_cierre_parcial",
            limit=limit,
            device_id=device_id,
        )
