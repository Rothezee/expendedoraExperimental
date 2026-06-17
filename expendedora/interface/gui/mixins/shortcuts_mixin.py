"""Mixin GUI: shortcuts_mixin."""

import json
from datetime import datetime
from pathlib import Path

from expendedora.interface.gui.constants import DEFAULT_PROMO_HOTKEYS


class ShortcutsMixin:
    def _normalizar_atajos_promociones(self, hotkeys_cfg):
        if not isinstance(hotkeys_cfg, dict):
            hotkeys_cfg = {}
        normalized = {}
        for promo, default_keys in DEFAULT_PROMO_HOTKEYS.items():
            raw = hotkeys_cfg.get(promo, default_keys)
            raw_is_list = isinstance(raw, list)
            if isinstance(raw, str):
                raw = [raw]
            if not isinstance(raw, list):
                raw = list(default_keys)
            clean = []
            for key in raw:
                key_str = str(key).strip()
                if key_str and key_str not in clean:
                    clean.append(key_str)
            # Si el usuario guardó explícitamente una promo sin atajos ([]), respetarlo.
            # Solo reponer defaults cuando el valor de entrada no era una lista válida.
            if not clean and not raw_is_list:
                clean = list(default_keys)
            normalized[promo] = clean
        return normalized


    def _load_shortcuts_from_file(self):
        try:
            shortcuts_path = Path(self.shortcuts_file)
            if not shortcuts_path.exists():
                return None
            with open(shortcuts_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
            if isinstance(payload, dict) and isinstance(payload.get("promociones"), dict):
                payload = payload.get("promociones")
            return self._normalizar_atajos_promociones(payload)
        except Exception as exc:
            print(f"[GUI] Aviso cargando atajos desde archivo: {exc}")
            return None


    def _save_shortcuts_to_file(self):
        payload = {
            "promociones": self._normalizar_atajos_promociones(self.atajos_promociones),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            shortcuts_path = Path(self.shortcuts_file)
            shortcuts_path.parent.mkdir(parents=True, exist_ok=True)
            with open(shortcuts_path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"[GUI] Aviso guardando atajos en archivo: {exc}")


    def _actualizar_candidatos_atajos(self):
        candidates = set()
        for keys in DEFAULT_PROMO_HOTKEYS.values():
            candidates.update(keys)
        for keys in self.atajos_promociones.values():
            candidates.update(keys)
        self._promo_binding_candidates = candidates

    def aplicar_atajos_promos_root(self):
        self._actualizar_candidatos_atajos()
        for key in self._promo_binding_candidates:
            self.root.unbind(key)
        for promo, keys in self.atajos_promociones.items():
            for key in keys:
                self.root.bind(key, lambda e, promo_name=promo: self._trigger_action(lambda: self.simular_promo(promo_name)))


    def aplicar_atajos_promos_entry(self, entry):
        self._actualizar_candidatos_atajos()
        for key in self._promo_binding_candidates:
            entry.unbind(key)
        for promo, keys in self.atajos_promociones.items():
            for key in keys:
                entry.bind(key, lambda e, promo_name=promo: self._trigger_action(lambda: self.simular_promo(promo_name)))

