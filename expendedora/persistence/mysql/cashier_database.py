import json
import os
from datetime import datetime

from expendedora.persistence.mysql.auth_repository import AuthRepositoryMySQL
from expendedora.persistence.json.config_repository import ConfigRepository
from expendedora.persistence.db_exception_message import format_db_exception
from expendedora.persistence.paths import CONFIG_FILE, PENDING_SYNC_FILE, ensure_persistence_dir


_auth_repo = AuthRepositoryMySQL(ConfigRepository(CONFIG_FILE))


def _load_pending_sync():
    if not os.path.exists(PENDING_SYNC_FILE):
        return []
    try:
        with open(PENDING_SYNC_FILE, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_pending_sync(items):
    ensure_persistence_dir()
    with open(PENDING_SYNC_FILE, "w", encoding="utf-8") as file_obj:
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
    for idx, item in enumerate(pending):
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
        hint = ""
        if "using password: NO" in msg or "Access denied" in msg:
            hint = " Revisá mysql.local.password en config.local.json (ver config.local.json.example)."
        print(f"[AUTH] Advertencia validando esquema: {msg}{hint}")
        return False, msg


def add_user(nombre, pin):
    # Intentar sincronizar pendientes primero (best-effort).
    try:
        _sync_pending_cashiers()
    except Exception:
        pass

    try:
        created_remote = _auth_repo.create_cashier(nombre, pin, require_remote=True)
        if created_remote:
            # Espejo en MySQL local para que login offline / active=local también encuentre al cajero.
            try:
                _auth_repo.create_cashier(nombre, pin, require_remote=False)
            except Exception:
                pass
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
        created_local = _auth_repo.create_cashier(nombre, pin, require_remote=False)
        _enqueue_pending_sync(nombre, pin)
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


def get_user(nombre, pin):
    # Cada login intenta drenar la cola pendiente de sincronización remota.
    try:
        _sync_pending_cashiers()
    except Exception:
        pass
    try:
        return _auth_repo.authenticate_cashier(nombre, pin)
    except Exception as exc:
        raise RuntimeError(format_db_exception(exc)) from exc
