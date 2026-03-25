import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config.json"
STATE_PATH = REPO_ROOT / "updater" / "last_update_state.json"
LOCK_PATH = REPO_ROOT / "updater" / "updater.lock"


def log(message: str):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[UPDATER {stamp}] {message}")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=check,
    )
    if result.stdout.strip():
        log(result.stdout.strip())
    if result.stderr.strip():
        log(result.stderr.strip())
    return result


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def load_updater_settings() -> dict:
    cfg = load_config().get("updater", {})
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "remote": str(cfg.get("remote", "origin")),
        "branch": str(cfg.get("branch", "main")),
        "check_interval_s": int(cfg.get("check_interval_s", 300)),
        "run_pip_install": bool(cfg.get("run_pip_install", False)),
        "requirements_file": str(cfg.get("requirements_file", "requirements.txt")),
        "restart_command_linux": str(cfg.get("restart_command_linux", "")),
        "restart_command_windows": str(cfg.get("restart_command_windows", "")),
        "preserve_files": list(cfg.get("preserve_files", ["config.json", "registro.json", "buffer_state.json"])),
    }


def current_platform_restart_command(settings: dict) -> str:
    if os.name == "nt":
        return settings.get("restart_command_windows", "").strip()
    return settings.get("restart_command_linux", "").strip()


def save_state(payload: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, indent=2)


def get_local_hash() -> str:
    return run(["git", "rev-parse", "HEAD"]).stdout.strip()


def get_remote_hash(remote: str, branch: str) -> str:
    return run(["git", "rev-parse", f"{remote}/{branch}"]).stdout.strip()


def backup_preserved_files(paths_to_preserve: list[str], backup_dir: Path):
    for relative in paths_to_preserve:
        rel_path = Path(relative)
        src = REPO_ROOT / rel_path
        if not src.exists():
            continue
        dst = backup_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def restore_preserved_files(backup_dir: Path):
    for item in backup_dir.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(backup_dir)
        dst = REPO_ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dst)


def maybe_install_requirements(settings: dict):
    if not settings.get("run_pip_install", False):
        return
    req_file = settings.get("requirements_file", "requirements.txt")
    req_path = REPO_ROOT / req_file
    if not req_path.exists():
        log(f"requirements file no encontrado: {req_file}")
        return
    log(f"Instalando dependencias desde {req_file}")
    run([sys.executable, "-m", "pip", "install", "-r", str(req_path)], check=True)


def maybe_restart_app(settings: dict):
    restart_cmd = current_platform_restart_command(settings)
    if not restart_cmd:
        log("Sin restart_command configurado; omito reinicio.")
        return
    log(f"Ejecutando reinicio: {restart_cmd}")
    subprocess.run(restart_cmd, cwd=str(REPO_ROOT), shell=True, check=False)


def _normalize_git_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def has_blocking_local_changes(preserve_files: list[str]) -> bool:
    result = run(["git", "status", "--porcelain"], check=True)
    changed = [line[3:].strip() for line in result.stdout.splitlines() if line.strip()]
    if not changed:
        return False
    preserve_set = {_normalize_git_path(p) for p in preserve_files}
    for item in changed:
        if _normalize_git_path(item) not in preserve_set:
            log(f"Cambio local bloqueante detectado: {item}")
            return True
    return False


def acquire_lock() -> bool:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        return False
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock():
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
    except Exception:
        pass


def run_once(force: bool = False) -> int:
    settings = load_updater_settings()
    if not settings["enabled"] and not force:
        log("Updater deshabilitado en config.json (updater.enabled=false).")
        return 0

    remote = settings["remote"]
    branch = settings["branch"]
    log(f"Buscando updates en {remote}/{branch}")
    if has_blocking_local_changes(settings["preserve_files"]):
        log("Updater cancelado por cambios locales no preservables.")
        return 1
    run(["git", "fetch", remote, branch], check=True)
    local_hash = get_local_hash()
    remote_hash = get_remote_hash(remote, branch)

    if local_hash == remote_hash and not force:
        log("No hay cambios remotos.")
        return 0

    with tempfile.TemporaryDirectory(prefix="expendedora-updater-") as tempdir:
        backup_dir = Path(tempdir) / "preserved"
        backup_preserved_files(settings["preserve_files"], backup_dir)

        log("Aplicando actualización de código...")
        run(["git", "reset", "--hard", f"{remote}/{branch}"], check=True)

        restore_preserved_files(backup_dir)
        maybe_install_requirements(settings)

    new_hash = get_local_hash()
    save_state(
        {
            "updated_at": datetime.now().isoformat(),
            "previous_hash": local_hash,
            "new_hash": new_hash,
            "remote": remote,
            "branch": branch,
        }
    )
    maybe_restart_app(settings)
    log(f"Update aplicado: {local_hash[:8]} -> {new_hash[:8]}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Auto updater de expendedora (Windows/Linux)")
    parser.add_argument("--once", action="store_true", help="Ejecutar una sola verificación.")
    parser.add_argument("--loop", action="store_true", help="Ejecutar en loop con intervalo de config.")
    parser.add_argument("--force", action="store_true", help="Aplicar update aunque no detecte cambio.")
    args = parser.parse_args()

    if not acquire_lock():
        log("Updater ya está en ejecución. Se cancela esta instancia.")
        return

    try:
        if args.loop:
            while True:
                try:
                    run_once(force=args.force)
                except Exception as exc:
                    log(f"Error en ciclo updater: {exc}")
                interval = load_updater_settings().get("check_interval_s", 300)
                time.sleep(max(30, int(interval)))
        else:
            run_once(force=args.force)
    finally:
        release_lock()


if __name__ == "__main__":
    main()

