from domain.models import SessionSnapshot


class SessionService:
    @staticmethod
    def build_daily_close(device_id: str, counters: dict):
        snap = SessionSnapshot.from_counters(device_id, counters)
        return {
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
        }

    @staticmethod
    def build_partial_close(device_id: str, counters: dict, employee_id: str):
        snap = SessionSnapshot.from_counters(device_id, counters)
        return {
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
        }

