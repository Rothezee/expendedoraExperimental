from expendedora.logic.domain.models import (
    COUNTER_DOMAIN_GLOBAL,
    COUNTER_DOMAIN_PARTIAL,
    LEGACY_COUNTER_DOMAIN_DAILY,
    LEGACY_COUNTER_DOMAIN_GLOBAL,
    LEGACY_COUNTER_DOMAIN_PARTIAL,
    Counters,
)


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

    @staticmethod
    def normalize_counter_domains(payload: dict | None) -> tuple[dict, dict]:
        raw = payload if isinstance(payload, dict) else {}
        global_candidates = [
            raw.get(COUNTER_DOMAIN_GLOBAL) or {},
            raw.get(LEGACY_COUNTER_DOMAIN_GLOBAL) or {},
            raw.get(LEGACY_COUNTER_DOMAIN_DAILY) or {},
        ]
        global_base = Counters().to_dict()
        for candidate in global_candidates:
            normalized = Counters.from_dict(candidate).to_dict()
            for key, value in normalized.items():
                try:
                    if float(value) > float(global_base.get(key, 0)):
                        global_base[key] = value
                except (TypeError, ValueError):
                    continue
        partial_src = (
            raw.get(COUNTER_DOMAIN_PARTIAL)
            or raw.get(LEGACY_COUNTER_DOMAIN_PARTIAL)
            or {}
        )
        return (
            global_base,
            Counters.from_dict(partial_src).to_dict(),
        )

