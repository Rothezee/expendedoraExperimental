"""Mensajes legibles para errores de BD (evita str() vacío o solo '0' en conectores/OS)."""

from __future__ import annotations


def format_db_exception(exc: BaseException, _depth: int = 0) -> str:
    if _depth > 6:
        return type(exc).__name__

    try:
        import mysql.connector
    except ImportError:
        mysql_error_type = ()
    else:
        mysql_error_type = (mysql.connector.Error,)

    if mysql_error_type and isinstance(exc, mysql_error_type):
        errno = getattr(exc, "errno", None)
        raw_msg = getattr(exc, "msg", None)
        msg = ("" if raw_msg is None else str(raw_msg)).strip()
        sqlstate = getattr(exc, "sqlstate", None)

        if not msg:
            inner = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
            if isinstance(inner, BaseException):
                im = format_db_exception(inner, _depth + 1)
                if im and im.strip() != "0":
                    msg = im

        if not msg and errno == 0:
            msg = (
                "Fallo de red o socket hacia MySQL (errno 0). Revisá host/puerto, "
                "que MySQL escuche red/IPv6, firewall y VPN."
            )
        elif not msg:
            msg = exc.__class__.__name__

        parts = [msg]
        if errno is not None and errno != 0:
            parts.append(f"[errno {errno}]")
        if sqlstate:
            parts.append(f"({sqlstate})")
        return " ".join(parts)

    if isinstance(exc, OSError):
        en = getattr(exc, "errno", None)
        wn = getattr(exc, "winerror", None)
        st = (exc.strerror or "").strip()
        bits = [st] if st else []
        if wn is not None:
            bits.append(f"winerror={wn}")
        elif en is not None:
            bits.append(f"os_errno={en}")
        if not bits:
            return f"{type(exc).__name__} {exc!r}"
        return f"{type(exc).__name__}: " + "; ".join(bits)

    inner = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if isinstance(inner, BaseException):
        nested = format_db_exception(inner, _depth + 1)
        if nested and nested != "0":
            return f"{type(exc).__name__}: {nested}"

    text = str(exc).strip()
    if text and text != "0" and text.lower() != "error 0":
        return text

    rep = repr(exc).strip("'\"")
    trivial = exc.__class__.__name__ == "RuntimeError" and rep in ("RuntimeError()", "RuntimeError")

    if trivial or not rep or rep == "0":
        return (
            "Fallo al conectar o consultar MySQL (sin mensaje del sistema). "
            'Revisá config.json → sección "mysql", objetos "local" y "production".'
        )
    detail = f"{type(exc).__name__}: {rep}"
    if detail and detail != "0":
        return detail
    return (
        'Fallo al conectar MySQL. Revisá config.json → "mysql"."local" y "mysql"."production".'
    )
