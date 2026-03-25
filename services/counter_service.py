from domain.models import Counters


class CounterService:
    @staticmethod
    def default_counters():
        return Counters().to_dict()

    @staticmethod
    def ensure_schema(data: dict | None):
        return Counters.from_dict(data or {}).to_dict()

    @staticmethod
    def has_activity(counters: dict) -> bool:
        normalized = Counters.from_dict(counters).to_dict()
        return any(
            normalized[key] > 0
            for key in (
                "fichas_expendidas",
                "dinero_ingresado",
                "promo1_contador",
                "promo2_contador",
                "promo3_contador",
                "fichas_devolucion",
                "fichas_cambio",
            )
        )

