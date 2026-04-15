from dataclasses import dataclass, field
from typing import Any, Dict, List


COUNTER_KEYS = (
    "fichas_expendidas",
    "dinero_ingresado",
    "promo1_contador",
    "promo2_contador",
    "promo3_contador",
    "fichas_restantes",
    "fichas_devolucion",
    "fichas_normales",
    "fichas_promocion",
    "fichas_cambio",
)


@dataclass
class Counters:
    fichas_expendidas: int = 0
    dinero_ingresado: float = 0.0
    promo1_contador: int = 0
    promo2_contador: int = 0
    promo3_contador: int = 0
    fichas_restantes: int = 0
    fichas_devolucion: int = 0
    fichas_normales: int = 0
    fichas_promocion: int = 0
    fichas_cambio: int = 0

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Counters":
        base = cls()
        if not isinstance(payload, dict):
            return base
        normalized = base.to_dict()
        for key in COUNTER_KEYS:
            if key in payload:
                normalized[key] = payload[key]
        return cls(**normalized)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fichas_expendidas": self.fichas_expendidas,
            "dinero_ingresado": self.dinero_ingresado,
            "promo1_contador": self.promo1_contador,
            "promo2_contador": self.promo2_contador,
            "promo3_contador": self.promo3_contador,
            "fichas_restantes": self.fichas_restantes,
            "fichas_devolucion": self.fichas_devolucion,
            "fichas_normales": self.fichas_normales,
            "fichas_promocion": self.fichas_promocion,
            "fichas_cambio": self.fichas_cambio,
        }


@dataclass
class MachineConfig:
    dni_admin: str = "00000000"
    codigo_hardware: str = ""
    tipo_maquina: int = 1
    api_base_urls: List[str] = field(default_factory=lambda: ["http://127.0.0.1", "https://app.maquinasbonus.com"])
    endpoint_receptor: str = "AdministrationPanel/src/devices/api_receptor.php"
    timeout_s: int = 5
    heartbeat_intervalo_s: int = 600


@dataclass
class TelemetryPayload:
    action: int
    dni_admin: str
    codigo_hardware: str
    tipo_maquina: int
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        body = {
            "action": self.action,
            "dni_admin": self.dni_admin,
            "codigo_hardware": self.codigo_hardware,
            "tipo_maquina": self.tipo_maquina,
        }
        if self.action == 2:
            body["payload"] = dict(self.payload)
        return body


@dataclass
class SessionSnapshot:
    device_id: str
    fichas_expendidas: int
    dinero_ingresado: float
    promo1_contador: int
    promo2_contador: int
    promo3_contador: int
    fichas_devolucion: int
    fichas_normales: int
    fichas_promocion: int
    fichas_cambio: int

    @classmethod
    def from_counters(cls, device_id: str, counters: Dict[str, Any]) -> "SessionSnapshot":
        model = Counters.from_dict(counters)
        return cls(
            device_id=device_id,
            fichas_expendidas=int(model.fichas_expendidas),
            dinero_ingresado=float(model.dinero_ingresado),
            promo1_contador=int(model.promo1_contador),
            promo2_contador=int(model.promo2_contador),
            promo3_contador=int(model.promo3_contador),
            fichas_devolucion=int(model.fichas_devolucion),
            fichas_normales=int(model.fichas_normales),
            fichas_promocion=int(model.fichas_promocion),
            fichas_cambio=int(model.fichas_cambio),
        )

