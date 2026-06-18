"""Utilidades compartidas para URLs del backend remoto."""


def es_url_local(base_url: str) -> bool:
    lower = str(base_url or "").lower()
    return "127.0.0.1" in lower or "localhost" in lower
