from __future__ import annotations

import mysql.connector

from infra.config_repository import ConfigRepository


class ReportRepositoryMySQL:
    def __init__(self, config_repository: ConfigRepository):
        self.config_repository = config_repository

    def _connect(self):
        last_exc = None
        for target in self.config_repository.iter_mysql_targets(prefer_local_first=True):
            try:
                return mysql.connector.connect(**target)
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
        columns = set()
        for row in cursor.fetchall():
            if isinstance(row, dict):
                # mysql.connector con dictionary=True devuelve claves como "Field".
                field_name = row.get("Field") or row.get("COLUMN_NAME")
                if field_name:
                    columns.add(str(field_name))
                continue
            # Compatibilidad con cursores tuple/list.
            if isinstance(row, (list, tuple)) and row:
                columns.add(str(row[0]))
        return columns

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
                resolved_device = self._resolve_device_id(cursor, device_id)
                if resolved_device is None:
                    # Si no podemos resolver el código hardware, no filtramos:
                    # mostrar datos es preferible a "0 filas" engañoso.
                    pass
                else:
                    sql += " WHERE id_dispositivo = %s"
                    params.append(resolved_device)
            sort_column = order_column if order_column in available else selected_columns[0]
            sql += f" ORDER BY {sort_column} DESC LIMIT %s"
            params.append(self._safe_limit(limit))
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _resolve_device_id(cursor, device_id: str) -> int | None:
        raw = str(device_id or "").strip()
        if not raw:
            return None
        if raw.isdigit():
            return int(raw)
        # Compatibilidad con el valor por defecto de GUI: codigo_hardware (ej: EXPENDEDORA_1).
        try:
            cursor.execute(
                "SELECT id_dispositivo FROM dispositivos WHERE codigo_hardware = %s LIMIT 1",
                (raw,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            if isinstance(row, dict):
                value = row.get("id_dispositivo")
            elif isinstance(row, (list, tuple)) and row:
                value = row[0]
            else:
                value = None
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    def fetch_daily_closures(self, limit: int = 50, device_id: str = ""):
        columns = [
            "id_cierre_diario",
            "id_cierre",
            "id_dispositivo",
            "fichas_totales",
            "dinero",
            "p1",
            "p2",
            "p3",
            "fichas_promo",
            "fichas_devolucion",
            "fichas_cambio",
            "fecha_apertura",
            "fecha_cierre",
            "tipo_evento",
        ]
        rows = self._select_rows(
            table="cierres_diarios",
            preferred_columns=columns,
            order_column="id_cierre",
            limit=limit,
            device_id=device_id,
        )
        for row in rows:
            if isinstance(row, dict):
                if "id_cierre" not in row and "id_cierre_diario" in row:
                    row["id_cierre"] = row.get("id_cierre_diario")
                if "tipo_evento" not in row:
                    row["tipo_evento"] = "cierre_diario"
        return rows

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

    def fetch_expendedora_telemetry(self, limit: int = 50, device_id: str = ""):
        columns = [
            "id_lectura",
            "id_dispositivo",
            "fichas",
            "dinero",
            "fecha_registro",
        ]
        return self._select_rows(
            table="telemetria_expendedoras",
            preferred_columns=columns,
            order_column="id_lectura",
            limit=limit,
            device_id=device_id,
        )
