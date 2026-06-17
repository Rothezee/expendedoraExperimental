"""
Persistencia atómica del estado operativo de la máquina (contadores + buffer).
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from expendedora.logic.domain.models import (
    COUNTER_DOMAIN_GLOBAL,
    COUNTER_DOMAIN_PARTIAL,
    COUNTER_KEYS,
    Counters,
    LEGACY_COUNTER_DOMAIN_DAILY,
    LEGACY_COUNTER_DOMAIN_GLOBAL,
    LEGACY_COUNTER_DOMAIN_PARTIAL,
)
from expendedora.persistence.paths import (
    CONFIG_FILE,
    LEGACY_BUFFER_FILE,
    REGISTRO_FILE,
    STATE_FILE,
)


def _ensure_counters(data: dict | None) -> dict:
    return Counters.from_dict(data or {}).to_dict()
SCHEMA_VERSION = 1

BUFFER_PERSISTED_KEYS = (
    "fichas_restantes",
    "fichas_expendidas",
    "fichas_expendidas_sesion",
    "cuenta",
    "r_cuenta",
)

MONOTONIC_COUNTER_KEYS = (
    "fichas_expendidas",
    "dinero_ingresado",
    "promo1_contador",
    "promo2_contador",
    "promo3_contador",
    "fichas_devolucion",
    "fichas_normales",
    "fichas_promocion",
    "fichas_cambio",
)

_revision = 0
_ATOMIC_REPLACE_RETRIES = 8
_ATOMIC_REPLACE_BASE_SLEEP_S = 0.02


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_load_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    """Escribe JSON de forma atómica (tmp + fsync + replace) con backup opcional."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    if os.path.exists(path):
        try:
            shutil.copy2(path, f"{path}.bak")
        except Exception:
            pass
    with open(tmp_path, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, indent=2)
        file_obj.flush()
        os.fsync(file_obj.fileno())
    replace_error: Optional[PermissionError] = None
    for attempt in range(_ATOMIC_REPLACE_RETRIES + 1):
        try:
            os.replace(tmp_path, path)
            replace_error = None
            break
        except PermissionError as exc:
            replace_error = exc
            if attempt >= _ATOMIC_REPLACE_RETRIES:
                break
            time.sleep(_ATOMIC_REPLACE_BASE_SLEEP_S * (attempt + 1))
    if replace_error is not None:
        raise PermissionError(
            f"No se pudo reemplazar '{path}' por bloqueo de archivo tras "
            f"{_ATOMIC_REPLACE_RETRIES + 1} intentos"
        ) from replace_error
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def default_buffer() -> Dict[str, Any]:
    return {
        "fichas_restantes": 0,
        "fichas_expendidas": 0,
        "fichas_expendidas_sesion": 0,
        "cuenta": 0,
        "r_cuenta": 0,
    }


def build_snapshot(
    *,
    buffer: Optional[Dict[str, Any]] = None,
    contadores_global: Optional[Dict[str, Any]] = None,
    contadores_parcial: Optional[Dict[str, Any]] = None,
    contadores: Optional[Dict[str, Any]] = None,
    contadores_apertura: Optional[Dict[str, Any]] = None,
    contadores_parciales: Optional[Dict[str, Any]] = None,
    pending_lots: Optional[list] = None,
    reason: str = "",
    revision: Optional[int] = None,
) -> Dict[str, Any]:
    global _revision
    buf = dict(default_buffer())
    if buffer:
        for key in BUFFER_PERSISTED_KEYS:
            if key in buffer:
                buf[key] = buffer[key]
    if revision is None:
        _revision += 1
        rev = _revision
    else:
        rev = revision
        _revision = max(_revision, rev)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "revision": rev,
        "updated_at": _now_iso(),
        "reason": reason,
        "buffer": buf,
        COUNTER_DOMAIN_GLOBAL: _ensure_counters(
            contadores_global or contadores or contadores_apertura
        ),
        COUNTER_DOMAIN_PARTIAL: _ensure_counters(
            contadores_parcial or contadores_parciales
        ),
    }
    if isinstance(pending_lots, list):
        snapshot["pending_lots"] = pending_lots
    return snapshot


def load_snapshot(path: str = STATE_FILE) -> Optional[Dict[str, Any]]:
    data = _safe_load_json(path)
    if data is None and os.path.exists(f"{path}.bak"):
        data = _safe_load_json(f"{path}.bak")
    if not data or data.get("schema_version") != SCHEMA_VERSION:
        return None
    global _revision
    try:
        _revision = max(_revision, int(data.get("revision", 0)))
    except (TypeError, ValueError):
        pass
    return data


def save_snapshot(
    snapshot: Dict[str, Any],
    path: str = STATE_FILE,
    *,
    sync_config: Optional[Dict[str, Any]] = None,
    config_path: str = CONFIG_FILE,
) -> Dict[str, Any]:
    """Persiste snapshot atómico; opcionalmente sincroniza contadores en config.json."""
    global _revision
    snap = dict(snapshot)
    try:
        current_rev = int(snap.get("revision", 0))
    except (TypeError, ValueError):
        current_rev = 0
    _revision = max(_revision, current_rev)
    _revision += 1
    snap["revision"] = _revision
    snap["updated_at"] = _now_iso()
    snap.setdefault("schema_version", SCHEMA_VERSION)
    atomic_write_json(path, snap)
    if sync_config is not None:
        sync_config = dict(sync_config)
        sync_config.pop(LEGACY_COUNTER_DOMAIN_GLOBAL, None)
        sync_config.pop(LEGACY_COUNTER_DOMAIN_DAILY, None)
        sync_config.pop(LEGACY_COUNTER_DOMAIN_PARTIAL, None)
        sync_config["updated_at"] = snap["updated_at"]
        cnt_global = _ensure_counters(
            snap.get(COUNTER_DOMAIN_GLOBAL) or snap.get(LEGACY_COUNTER_DOMAIN_GLOBAL)
        )
        cnt_partial = _ensure_counters(
            snap.get(COUNTER_DOMAIN_PARTIAL) or snap.get(LEGACY_COUNTER_DOMAIN_PARTIAL)
        )
        try:
            buf_fr = max(0, int((snap.get("buffer") or {}).get("fichas_restantes", 0)))
            cnt_global["fichas_restantes"] = buf_fr
        except (TypeError, ValueError):
            pass
        sync_config[COUNTER_DOMAIN_GLOBAL] = cnt_global
        sync_config[COUNTER_DOMAIN_PARTIAL] = cnt_partial
        atomic_write_json(config_path, sync_config)
    return snap


def save_buffer_only(buffer_data: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    """Persiste solo campos de buffer (cuando la GUI aún no actualizó contadores)."""
    existing = load_snapshot() or build_snapshot(reason="init")
    existing["buffer"] = dict(default_buffer())
    for key in BUFFER_PERSISTED_KEYS:
        if key in buffer_data:
            existing["buffer"][key] = buffer_data[key]
    existing["reason"] = reason
    return save_snapshot(existing)


def _merge_counters(target: Dict[str, Any], source: Dict[str, Any], source_ts: str) -> None:
    for key in COUNTER_KEYS:
        try:
            src_val = source.get(key, target.get(key, 0))
            tgt_val = target.get(key, 0)
            if key == "fichas_restantes":
                continue
            if key in MONOTONIC_COUNTER_KEYS or key == "dinero_ingresado":
                if isinstance(src_val, (int, float)) and isinstance(tgt_val, (int, float)):
                    target[key] = max(src_val, tgt_val)
            else:
                if isinstance(src_val, (int, float)) and src_val > tgt_val:
                    target[key] = src_val
        except (TypeError, ValueError):
            continue
    target["_source_ts"] = source_ts


def _pick_fichas_restantes(candidates: List[Tuple[int, str]]) -> int:
    """Elige fichas_restantes: fuente con updated_at más reciente; empate → max."""
    if not candidates:
        return 0
    parsed: List[Tuple[int, str, datetime]] = []
    for value, ts in candidates:
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt = datetime.min
        parsed.append((int(value), ts, dt))
    parsed.sort(key=lambda x: (x[2], x[0]), reverse=True)
    return parsed[0][0]


def recover_state(
    config_path: str = CONFIG_FILE,
    buffer_path: str = LEGACY_BUFFER_FILE,
    registro_path: str = REGISTRO_FILE,
    state_path: str = STATE_FILE,
) -> Dict[str, Any]:
    """
    Fusiona machine_state, config, buffer_state y registro; persiste snapshot unificado.
    """
    sources: List[str] = []
    candidates_restantes: List[Tuple[int, str]] = []

    machine = load_snapshot(state_path)
    if machine:
        sources.append("machine_state")

    config = _safe_load_json(config_path)
    if config:
        sources.append("config")

    legacy_buffer = _safe_load_json(buffer_path)
    if legacy_buffer:
        sources.append("buffer_state")

    registro = _safe_load_json(registro_path)

    result = build_snapshot(reason="recover")
    ts_default = _now_iso()
    explicit_fichas_from_config = False
    machine_buffer_restantes: Optional[int] = None

    if machine:
        result["updated_at"] = machine.get("updated_at", ts_default)
        ts_m = result["updated_at"]
        buf = machine.get("buffer") or {}
        for key in BUFFER_PERSISTED_KEYS:
            if key in buf:
                result["buffer"][key] = buf[key]
        _merge_counters(
            result[COUNTER_DOMAIN_GLOBAL],
            machine.get(COUNTER_DOMAIN_GLOBAL)
            or machine.get(LEGACY_COUNTER_DOMAIN_GLOBAL)
            or machine.get(LEGACY_COUNTER_DOMAIN_DAILY)
            or {},
            ts_m,
        )
        _merge_counters(
            result[COUNTER_DOMAIN_PARTIAL],
            machine.get(COUNTER_DOMAIN_PARTIAL)
            or machine.get(LEGACY_COUNTER_DOMAIN_PARTIAL)
            or {},
            ts_m,
        )
        candidates_restantes.append(
            (int(result["buffer"].get("fichas_restantes", 0)), ts_m)
        )
        machine_buffer_restantes = int(result["buffer"].get("fichas_restantes", 0))

    if config:
        ts_c = config.get("updated_at", ts_default) if isinstance(config.get("updated_at"), str) else ts_default
        global_cfg = (
            config.get(COUNTER_DOMAIN_GLOBAL)
            or config.get(LEGACY_COUNTER_DOMAIN_GLOBAL)
            or config.get(LEGACY_COUNTER_DOMAIN_DAILY)
            or {}
        )
        partial_cfg = (
            config.get(COUNTER_DOMAIN_PARTIAL)
            or config.get(LEGACY_COUNTER_DOMAIN_PARTIAL)
            or {}
        )
        _merge_counters(result[COUNTER_DOMAIN_GLOBAL], global_cfg, ts_c)
        _merge_counters(result[COUNTER_DOMAIN_PARTIAL], partial_cfg, ts_c)
        cnt = global_cfg
        # fichas_restantes vive en machine_state.buffer; config no debe pisarlo al recuperar.
        if machine is None and "fichas_restantes" in cnt:
            candidates_restantes.append((int(cnt["fichas_restantes"]), ts_c))
        if "fichas_expendidas" in cnt:
            explicit_fichas_from_config = True
            try:
                result["buffer"]["fichas_expendidas"] = max(
                    int(result["buffer"].get("fichas_expendidas", 0)),
                    int(cnt["fichas_expendidas"]),
                )
            except (TypeError, ValueError):
                pass
        if "dinero_ingresado" in cnt:
            try:
                result["buffer"]["r_cuenta"] = max(
                    float(result["buffer"].get("r_cuenta", 0)),
                    float(cnt["dinero_ingresado"]),
                )
            except (TypeError, ValueError):
                pass

    if legacy_buffer:
        ts_b = ts_default
        if os.path.exists(buffer_path):
            try:
                ts_b = datetime.fromtimestamp(os.path.getmtime(buffer_path)).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                pass
        for key in ("fichas_expendidas", "fichas_expendidas_sesion", "cuenta", "r_cuenta"):
            if key in legacy_buffer:
                try:
                    cur = result["buffer"].get(key, 0)
                    val = legacy_buffer[key]
                    result["buffer"][key] = max(cur, val) if key != "r_cuenta" else max(float(cur), float(val))
                except (TypeError, ValueError):
                    result["buffer"][key] = legacy_buffer[key]
        if machine is None and "fichas_restantes" in legacy_buffer:
            candidates_restantes.append((int(legacy_buffer["fichas_restantes"]), ts_b))
        _merge_counters(
            result[COUNTER_DOMAIN_GLOBAL],
            {
                "fichas_restantes": legacy_buffer.get("fichas_restantes", 0),
                "fichas_expendidas": legacy_buffer.get("fichas_expendidas", 0),
                "dinero_ingresado": legacy_buffer.get("r_cuenta", 0),
            },
            ts_b,
        )

    if registro:
        sources.append("registro")
        try:
            reg_fichas = int(registro.get("fichas_expendidas", 0))
            # Evitar "resucitar" contadores tras un reset explícito de sesión:
            # usar registro solo como fallback cuando el estado recuperado aún está en cero.
            recovered_global = int(result[COUNTER_DOMAIN_GLOBAL].get("fichas_expendidas", 0))
            recovered_buffer = int(result["buffer"].get("fichas_expendidas", 0))
            if (
                not explicit_fichas_from_config
                and recovered_global <= 0
                and recovered_buffer <= 0
                and reg_fichas > 0
            ):
                result[COUNTER_DOMAIN_GLOBAL]["fichas_expendidas"] = reg_fichas
                result["buffer"]["fichas_expendidas"] = reg_fichas
        except (TypeError, ValueError):
            pass

    if machine_buffer_restantes is not None:
        restantes = max(0, machine_buffer_restantes)
    else:
        restantes = _pick_fichas_restantes(candidates_restantes)
    result["buffer"]["fichas_restantes"] = restantes
    result[COUNTER_DOMAIN_GLOBAL]["fichas_restantes"] = restantes
    if restantes <= 0:
        result["pending_lots"] = []
    elif machine and isinstance(machine.get("pending_lots"), list):
        result["pending_lots"] = machine.get("pending_lots")

    for section in (COUNTER_DOMAIN_GLOBAL, COUNTER_DOMAIN_PARTIAL):
        if section in result and isinstance(result[section], dict):
            result[section].pop("_source_ts", None)

    result[COUNTER_DOMAIN_GLOBAL] = _ensure_counters(result.get(COUNTER_DOMAIN_GLOBAL))
    result[COUNTER_DOMAIN_PARTIAL] = _ensure_counters(result.get(COUNTER_DOMAIN_PARTIAL))
    buf = result.get("buffer") or {}
    for key in ("fichas_restantes", "fichas_expendidas", "fichas_expendidas_sesion", "cuenta"):
        if key in buf:
            try:
                buf[key] = max(0, int(buf[key]))
            except (TypeError, ValueError):
                buf[key] = 0
    if "r_cuenta" in buf:
        try:
            buf["r_cuenta"] = max(0.0, float(buf["r_cuenta"]))
        except (TypeError, ValueError):
            buf["r_cuenta"] = 0.0
    result["buffer"] = buf

    result["reason"] = "recover"
    source_label = "+".join(sources) if sources else "defaults"
    print(f"[STATE] Recuperado desde: {source_label}")

    save_snapshot(result, path=state_path)
    return result


def get_recovered_counters(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    cnt_global = _ensure_counters(
        snapshot.get(COUNTER_DOMAIN_GLOBAL)
        or snapshot.get(LEGACY_COUNTER_DOMAIN_GLOBAL)
        or snapshot.get(LEGACY_COUNTER_DOMAIN_DAILY)
    )
    cnt_partial = _ensure_counters(
        snapshot.get(COUNTER_DOMAIN_PARTIAL)
        or snapshot.get(LEGACY_COUNTER_DOMAIN_PARTIAL)
    )
    pending_lots = snapshot.get("pending_lots")
    return {
        COUNTER_DOMAIN_GLOBAL: cnt_global,
        COUNTER_DOMAIN_PARTIAL: cnt_partial,
        "buffer": dict(snapshot.get("buffer") or default_buffer()),
        "pending_lots": pending_lots if isinstance(pending_lots, list) else [],
    }
