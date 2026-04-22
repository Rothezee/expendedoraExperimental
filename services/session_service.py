from datetime import datetime

from domain.models import SessionSnapshot


class SessionService:
    @staticmethod
    def build_daily_close(device_id: str, counters: dict, event_type: str = "cierre"):
        snap = SessionSnapshot.from_counters(device_id, counters)
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            # Campos legacy (compatibles con backend actual)
            "id_expendedora": snap.device_id,
            "fichas_expendidas": snap.fichas_expendidas,
            "dinero_ingresado": snap.dinero_ingresado,
            "promo1_contador": snap.promo1_contador,
            "promo2_contador": snap.promo2_contador,
            "promo3_contador": snap.promo3_contador,
            "fichas_devolucion": snap.fichas_devolucion,
            "fichas_normales": snap.fichas_normales,
            "fichas_promocion": snap.fichas_promocion,
            "fichas_cambio": snap.fichas_cambio,
            # Campos alineados a tabla cierres_diarios
            "id_dispositivo": snap.device_id,
            "fichas_totales": snap.fichas_expendidas,
            "dinero": snap.dinero_ingresado,
            "p1": snap.promo1_contador,
            "p2": snap.promo2_contador,
            "p3": snap.promo3_contador,
            "fichas_promo": snap.fichas_promocion,
            "fecha_apertura": fecha_actual,
            "tipo_evento": event_type,
        }

    @staticmethod
    def build_partial_close(device_id: str, counters: dict, employee_id: str, cashier_id: int | None = None):
        snap = SessionSnapshot.from_counters(device_id, counters)
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        resolved_cashier_id = cashier_id if cashier_id is not None else employee_id
        return {
            # Campos legacy (compatibles con backend actual)
            "cierre_expendedora_id": snap.device_id,
            "partial_fichas": snap.fichas_expendidas,
            "partial_dinero": snap.dinero_ingresado,
            "partial_p1": snap.promo1_contador,
            "partial_p2": snap.promo2_contador,
            "partial_p3": snap.promo3_contador,
            "partial_devolucion": snap.fichas_devolucion,
            "partial_normales": snap.fichas_normales,
            "partial_promocion": snap.fichas_promocion,
            "partial_cambio": snap.fichas_cambio,
            "employee_id": employee_id,
            "usuario_cajero": employee_id,
            "username_cajero": employee_id,
            # Campos alineados a tabla cierres_parciales
            "id_dispositivo": snap.device_id,
            "id_cajero": resolved_cashier_id,
            "fichas_totales": snap.fichas_expendidas,
            "dinero": snap.dinero_ingresado,
            "p1": snap.promo1_contador,
            "p2": snap.promo2_contador,
            "p3": snap.promo3_contador,
            "fichas_promo": snap.fichas_promocion,
            "fichas_devolucion": snap.fichas_devolucion,
            "fichas_cambio": snap.fichas_cambio,
            "fecha_apertura_turno": fecha_actual,
        }

