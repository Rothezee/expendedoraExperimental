from expendedora.logic.domain.models import Counters


class CounterService:
    @staticmethod
    def default_counters():
        return Counters().to_dict()

    @staticmethod
    def ensure_schema(data: dict | None):
        return Counters.from_dict(data or {}).to_dict()
