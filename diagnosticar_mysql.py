import argparse
import json
import socket
import sys
from pathlib import Path


def _load_mysql_profile(config_path: Path, profile: str) -> dict:
    with config_path.open("r", encoding="utf-8") as file_obj:
        cfg = json.load(file_obj)
    mysql_cfg = cfg.get("mysql", {})
    if not isinstance(mysql_cfg, dict):
        raise ValueError("Sección 'mysql' inválida en config.json")
    profile_cfg = mysql_cfg.get(profile, {})
    if not isinstance(profile_cfg, dict):
        raise ValueError(f"Perfil mysql.{profile} inválido en config.json")
    required = ("host", "port", "user", "password", "database")
    missing = [key for key in required if key not in profile_cfg]
    if missing:
        raise ValueError(f"Faltan campos en mysql.{profile}: {', '.join(missing)}")
    return profile_cfg


def _resolve_host(host: str, port: int, force_ipv4: bool, force_ipv6: bool):
    family = socket.AF_UNSPEC
    if force_ipv4:
        family = socket.AF_INET
    elif force_ipv6:
        family = socket.AF_INET6

    infos = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM)
    unique = []
    seen = set()
    for family, socktype, proto, canonname, sockaddr in infos:
        ip = sockaddr[0]
        key = (family, ip)
        if key in seen:
            continue
        seen.add(key)
        unique.append((family, ip))
    return unique


def _check_tcp(ip: str, port: int, timeout_s: float, family: int) -> tuple[bool, str]:
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_s)
            sock.connect((ip, port))
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def _mysql_login_check(profile_cfg: dict, timeout_s: float):
    try:
        import mysql.connector as mc
    except Exception as exc:
        return False, f"No se pudo importar mysql.connector: {exc}"

    conn = None
    try:
        conn = mc.connect(
            host=str(profile_cfg["host"]),
            port=int(profile_cfg["port"]),
            user=str(profile_cfg["user"]),
            password=str(profile_cfg["password"]),
            database=str(profile_cfg["database"]),
            connection_timeout=max(1, int(timeout_s)),
            auth_plugin="mysql_native_password",
        )
        cur = conn.cursor()
        cur.execute("SELECT USER(), CURRENT_USER(), DATABASE()")
        row = cur.fetchone()
        return True, f"Login OK -> USER={row[0]} CURRENT_USER={row[1]} DB={row[2]}"
    except Exception as exc:
        return False, str(exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _print_1045_hint(error_text: str):
    if "1045" not in error_text and "Access denied" not in error_text:
        return
    print("\nSugerencia para error 1045:")
    print("- El usuario existe, pero no tiene permiso desde el host/IP actual.")
    print("- Verificá grants en el servidor MySQL:")
    print("  SELECT User, Host FROM mysql.user WHERE User='<usuario>';")
    print("  SHOW GRANTS FOR '<usuario>'@'<host>';")
    print("- Si conectás por IPv6, el Host debe cubrir ese prefijo (ej: 2802:....:%).")


def main():
    parser = argparse.ArgumentParser(
        description="Diagnóstico de conectividad/auth MySQL usando config.json"
    )
    parser.add_argument("--config", default="config.json", help="Ruta a config.json")
    parser.add_argument(
        "--profile",
        default="production",
        choices=["production", "local"],
        help="Perfil mysql a probar",
    )
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout en segundos")
    parser.add_argument("--ipv4", action="store_true", help="Forzar resolución IPv4")
    parser.add_argument("--ipv6", action="store_true", help="Forzar resolución IPv6")
    args = parser.parse_args()

    if args.ipv4 and args.ipv6:
        print("No podés usar --ipv4 y --ipv6 al mismo tiempo.")
        return 2

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"No existe {config_path}")
        return 2

    try:
        profile_cfg = _load_mysql_profile(config_path, args.profile)
    except Exception as exc:
        print(f"Error leyendo config: {exc}")
        return 2

    host = str(profile_cfg["host"])
    port = int(profile_cfg["port"])
    user = str(profile_cfg["user"])
    db_name = str(profile_cfg["database"])

    print(f"Perfil mysql: {args.profile}")
    print(f"Host: {host}  Puerto: {port}")
    print(f"Usuario: {user}  DB: {db_name}")
    print("-" * 72)

    try:
        addrs = _resolve_host(host, port, args.ipv4, args.ipv6)
    except Exception as exc:
        print(f"Resolución DNS/IP FALLÓ: {exc}")
        return 1

    if not addrs:
        print("Resolución DNS/IP FALLÓ: sin direcciones.")
        return 1

    print("Direcciones resueltas:")
    for family, ip in addrs:
        fam = "IPv6" if family == socket.AF_INET6 else "IPv4"
        print(f"- {fam}: {ip}")

    print("-" * 72)
    tcp_ok = False
    for family, ip in addrs:
        fam = "IPv6" if family == socket.AF_INET6 else "IPv4"
        ok, detail = _check_tcp(ip, port, args.timeout, family)
        state = "OK" if ok else "FALLÓ"
        print(f"TCP {fam} {ip}:{port} -> {state} ({detail})")
        if ok:
            tcp_ok = True

    print("-" * 72)
    login_ok, login_detail = _mysql_login_check(profile_cfg, args.timeout)
    if login_ok:
        print(f"MySQL login -> OK ({login_detail})")
        return 0

    print(f"MySQL login -> FALLÓ ({login_detail})")
    _print_1045_hint(login_detail.replace(user, "<usuario>"))
    if not tcp_ok:
        print("\nDiagnóstico final: el puerto no abre en ninguna IP resuelta.")
    else:
        print("\nDiagnóstico final: red/puerto disponibles, pero autenticación rechazada.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
