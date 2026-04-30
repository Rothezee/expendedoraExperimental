import json
import os
from datetime import datetime

from infra.auth_repository_mysql import AuthRepositoryMySQL
from infra.config_repository import ConfigRepository
from infra.db_exception_message import format_db_exception


_auth_repo = AuthRepositoryMySQL(ConfigRepository("config.json"))
_PENDING_SYNC_FILE = "pending_cashier_sync.json"


def _load_pending_sync():
    if not os.path.exists(_PENDING_SYNC_FILE):
        return []
    try:
        with open(_PENDING_SYNC_FILE, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_pending_sync(items):
    with open(_PENDING_SYNC_FILE, "w", encoding="utf-8") as file_obj:
        json.dump(items, file_obj, indent=2, ensure_ascii=False)


def _enqueue_pending_sync(username: str, pin: str):
    pending = _load_pending_sync()
    for idx, item in enumerate(pending):
        if item.get("username") == username:
            # Actualizamos pin por si se volvió a registrar offline con uno nuevo.
            item["pin"] = pin
            item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save_pending_sync(pending)
            return
    pending.append(
        {
            "username": username,
            "pin": pin,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    _save_pending_sync(pending)


def _sync_pending_cashiers():
    pending = _load_pending_sync()
    if not pending:
        return

    remaining = []
    for item in pending:
        username = str(item.get("username", "")).strip()
        pin = str(item.get("pin", "")).strip()
        if not username or not pin:
            continue
        try:
            # True (creado) o False (ya existía) => sincronizado OK.
            _auth_repo.create_cashier(username, pin, require_remote=True)
        except ConnectionError:
            remaining.append(item)
            # Si no hay conectividad remota, no seguimos intentando en este ciclo.
            remaining.extend(pending[idx + 1 :])
            break
        except Exception:
            remaining.append(item)

    _save_pending_sync(remaining)


def create_table():
    try:
        _auth_repo.check_schema()
        return True, ""
    except Exception as exc:
        msg = format_db_exception(exc)
        print(f"[AUTH] Advertencia validando esquema: {msg}")
        return False, msg


def add_user(nombre, contraceña):
    # Intentar sincronizar pendientes primero (best-effort).
    try:
        _sync_pending_cashiers()
    except Exception:
        pass

    try:
        created_remote = _auth_repo.create_cashier(nombre, contraceña, require_remote=True)
        if created_remote:
            return {
                "ok": True,
                "mode": "remote",
                "message": "Registro exitoso en panel remoto.",
            }
        return {
            "ok": False,
            "mode": "remote_exists",
            "message": "El usuario ya existe en el panel remoto.",
        }
    except ConnectionError:
        # Fallback offline: crear local y dejar pendiente sincronización remota.
        created_local = _auth_repo.create_cashier(nombre, contraceña, require_remote=False)
        _enqueue_pending_sync(nombre, contraceña)
        if created_local:
            return {
                "ok": True,
                "mode": "offline_pending",
                "message": "Sin conexión remota: usuario creado en local y pendiente de sincronizar.",
            }
        return {
            "ok": True,
            "mode": "offline_pending_exists",
            "message": "Sin conexión remota: usuario ya existía localmente y quedó pendiente de sincronizar.",
        }


def get_user(nombre, contraceña):
    # Cada login intenta drenar la cola pendiente de sincronización remota.
    try:
        _sync_pending_cashiers()
    except Exception:
        pass
    try:
        return _auth_repo.authenticate_cashier(nombre, contraceña)
    except Exception as exc:
        raise RuntimeError(format_db_exception(exc)) from exc