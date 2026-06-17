"""Mixin GUI: configuración y persistencia GUI."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class ConfigMixin:
    def _sync_counter_aliases(self):
        """
        Alias legacy temporal:
        - contadores         -> contadores_parcial (sesión / GUI operativa)
        - contadores_apertura-> contadores_global (cierre diario)
        - contadores_parciales -> contadores_parcial
        """
        self.contadores = self.contadores_parcial
        self.contadores_apertura = self.contadores_global
        self.contadores_parciales = self.contadores_parcial


    def _increment_contador_operacion(self, key, amount=1):
        """Incrementa un contador en sesión (GUI) y en acumulado global (cierre diario)."""
        if key == "dinero_ingresado":
            self.contadores_parcial[key] = float(self.contadores_parcial.get(key, 0)) + float(amount)
            self.contadores_global[key] = float(self.contadores_global.get(key, 0)) + float(amount)
        else:
            self.contadores_parcial[key] = int(self.contadores_parcial.get(key, 0)) + int(amount)
            self.contadores_global[key] = int(self.contadores_global.get(key, 0)) + int(amount)


    def _decrement_contador_operacion(self, key, amount=1):
        """Decrementa un contador en sesión y global (revertir fichas no dispensadas)."""
        if key == "dinero_ingresado":
            self.contadores_parcial[key] = max(0.0, float(self.contadores_parcial.get(key, 0)) - float(amount))
            self.contadores_global[key] = max(0.0, float(self.contadores_global.get(key, 0)) - float(amount))
        else:
            self.contadores_parcial[key] = max(0, int(self.contadores_parcial.get(key, 0)) - int(amount))
            self.contadores_global[key] = max(0, int(self.contadores_global.get(key, 0)) - int(amount))


    def _aplicar_atribucion_token(self, attr: dict) -> None:
        """Incrementa contadores de fichas paso a paso (cada TOKEN)."""
        if not isinstance(attr, dict):
            return
        for key in ("fichas_normales", "fichas_devolucion", "fichas_cambio", "fichas_promocion"):
            qty = int(attr.get(key, 0) or 0)
            if qty > 0:
                self._increment_contador_operacion(key, qty)

    def _revert_pending_counter_attribution(self, revert: dict):
        """Anula venta: dinero/promo al inicio; fichas solo las que salieron."""
        payload = dict(revert or {})
        fichas_disp = int(
            payload.pop("fichas_dispensadas", 0) or payload.pop("fichas_hw_revert", 0) or 0
        )
        payload.pop("fichas_venta", None)
        payload.pop("fichas_pendientes", None)
        for key, amount in payload.items():
            if not amount:
                continue
            self._decrement_contador_operacion(key, amount)
        if fichas_disp > 0:
            self._ms.revert_fichas_sesion_hw(fichas_disp, immediate=False)
        if revert.get("dinero_ingresado"):
            dinero = float(self.contadores_parcial.get("dinero_ingresado", 0))
            self._ms.set_r_cuenta(dinero, immediate=False)
            self._ms.set_cuenta(dinero, immediate=False)
        self._recalcular_bases_contadores()
        self.actualizar_contadores_gui()


    def cargar_configuracion(self):
        config = self.config_repository.load()
        self.promociones = config.get("promociones") or self.promociones
        if not all(p in self.promociones for p in ("Promo 1", "Promo 2", "Promo 3")):
            for nombre in ("Promo 1", "Promo 2", "Promo 3"):
                self.promociones.setdefault(nombre, {"precio": 0, "fichas": 0})
        for promo_name, promo_cfg in list(self.promociones.items()):
            if not isinstance(promo_cfg, dict):
                self.promociones[promo_name] = {"precio": 0.0, "fichas": 0}
                continue
            promo_cfg["precio"] = float(promo_cfg.get("precio", 0) or 0)
            promo_cfg["fichas"] = max(0, int(float(promo_cfg.get("fichas", 0) or 0)))
        self.valor_ficha = config.get("valor_ficha", self.valor_ficha)
        self.device_id = config.get("device_id", self.device_id)
        self.codigo_hardware = config.get("maquina", {}).get("codigo_hardware", self.device_id)
        self.dni_admin = config.get("admin", {}).get("dni_admin", self.dni_admin)
        self.api_config = config.get("api", self.api_config)
        self.heartbeat_intervalo_s = config.get("heartbeat", {}).get("intervalo_s", self.heartbeat_intervalo_s)
        self.maquina_hoppers = config.get("maquina", {}).get("hoppers", self.maquina_hoppers)
        self.atajos_promociones = self._normalizar_atajos_promociones(config.get("atajos", {}).get("promociones", self.atajos_promociones))
        shortcuts_file_data = self._load_shortcuts_from_file()
        if isinstance(shortcuts_file_data, dict):
            self.atajos_promociones = shortcuts_file_data
        self.operacion_config = config.get("operacion", self.operacion_config)
        if not isinstance(self.operacion_config, dict):
            self.operacion_config = {"ultima_apertura_fecha": ""}
        self.network_manager_cfg = config.get("network_manager", self.network_manager_cfg)
        if not isinstance(self.network_manager_cfg, dict):
            self.network_manager_cfg = {
                "enabled": True,
                "check_interval_s": 8,
                "reconnect_after_failures": 3,
                "backend_timeout_s": 3.0,
                "internet_host": "8.8.8.8",
                "backend_url": "",
                "preferred_interface": "",
                "wifi_ssid": "",
                "wifi_password": "",
            }
        if not str(self.network_manager_cfg.get("backend_url", "")).strip():
            self.network_manager_cfg["backend_url"] = self._build_backend_probe_url()
        self.contadores_global = self.counter_service.ensure_schema(
            config.get("contadores_global", config.get("contadores", self.contadores_global))
        )
        self.contadores_parcial = self.counter_service.ensure_schema(
            config.get("contadores_parcial", config.get("contadores_parciales", self.contadores_parcial))
        )
        self._sync_counter_aliases()
        self._last_tolvas_signature = None
        self._last_tolva_ids = None
        try:
            self.app.recargar_tolvas_desde_config()
        except Exception as exc:
            print(f"[GUI] Recarga de tolvas tras config: {exc}")
        if getattr(self, "root", None):
            try:
                self.root.after(0, self.actualizar_tolvas_gui)
            except Exception:
                pass


    def _aplicar_estado_recuperado(self):
        """Aplica snapshot recuperado por el core (post-corte / arranque)."""
        recovered = None
        try:
            recovered = self.app.get_recovered_state()
        except Exception as exc:
            print(f"[GUI] Sin estado recuperado del core: {exc}")
        if not recovered:
            return
        self.contadores_global = self.counter_service.ensure_schema(
            recovered.get("contadores_global", recovered.get("contadores", self.contadores_global))
        )
        self.contadores_parcial = self.counter_service.ensure_schema(
            recovered.get("contadores_parcial", recovered.get("contadores_parciales", self.contadores_parcial))
        )
        self._sync_counter_aliases()
        buf = recovered.get("buffer") or {}
        restantes = int(buf.get("fichas_restantes", self.contadores.get("fichas_restantes", 0)))
        self.contadores["fichas_restantes"] = restantes
        self._ms.register_gui_counters(
            self.contadores_global, self.contadores_global, self.contadores_parcial
        )
        self._recalcular_bases_contadores()
        if getattr(self, "contadores_labels", None):
            self.actualizar_contadores_gui()


    def _sanear_contadores_gui(self) -> None:
        """Impide contadores negativos y corrige fichas_expendidas corruptas tras corte."""
        self.contadores_global = self.counter_service.ensure_schema(self.contadores_global)
        self.contadores_parcial = self.counter_service.ensure_schema(self.contadores_parcial)
        self._sync_counter_aliases()
        if int(self.contadores_global.get("fichas_expendidas", 0)) < 0:
            fallback = max(0, int(self.contadores_parcial.get("fichas_expendidas", 0)))
            self.contadores_global["fichas_expendidas"] = fallback
        if int(self.contadores_parcial.get("fichas_expendidas", 0)) < 0:
            self.contadores_parcial["fichas_expendidas"] = max(
                0, int(self.contadores_global.get("fichas_expendidas", 0))
            )


    def _recalcular_bases_contadores(self):
        """Base + sesión HW (fichas contadas paso a paso al dispensar)."""
        self._sanear_contadores_gui()
        sesion = max(0, int(self._ms.get_fichas_sesion()))
        self.inicio_apertura_fichas = int(self.contadores_global["fichas_expendidas"]) - sesion
        self.inicio_parcial_fichas = int(self.contadores_parcial["fichas_expendidas"]) - sesion
        self.contadores_global["fichas_expendidas"] = max(0, self.inicio_apertura_fichas + sesion)
        self.contadores_parcial["fichas_expendidas"] = max(0, self.inicio_parcial_fichas + sesion)
        self._sync_counter_aliases()


    def _persistir_estado_critico(self, reason: str):
        """Snapshot atómico de contadores + buffer; sincroniza config.json."""
        self._sanear_contadores_gui()
        self.contadores["fichas_restantes"] = max(0, int(self._ms.get_fichas_restantes()))
        self._ms.set_fichas_restantes(self.contadores["fichas_restantes"], immediate=False)
        self._ms.set_r_cuenta(float(self.contadores_parcial["dinero_ingresado"]), immediate=False)
        self.app.persist_snapshot(
            contadores_global=self.contadores_global,
            contadores_parcial=self.contadores_parcial,
            operacion=self.operacion_config,
            reason=reason,
        )


    def guardar_configuracion(self, inmediato=False):
        """
        Guarda config.json con debounce: espera 1.5s de inactividad antes de escribir.
        Usar inmediato=True solo cuando sea estrictamente necesario (cierre, sesión).
        Evita escribir a disco en cada ficha dispensada (muy costoso en SD card).
        """
        if inmediato:
            self._escribir_config_ahora()
            return
        # Cancelar timer anterior y arrancar uno nuevo (debounce 1.5s)
        if self._guardar_config_timer is not None:
            self._guardar_config_timer.cancel()
        import threading as _t
        self._guardar_config_timer = _t.Timer(1.5, lambda: self.root.after(0, self._escribir_config_ahora))
        self._guardar_config_timer.daemon = True
        self._guardar_config_timer.start()


    def _escribir_config_ahora(self):
        """Escribe config.json al disco (siempre en el hilo de Tkinter)."""
        codigo_hardware = self.codigo_hardware or self.device_id
        existing = self.config_repository.load()
        base_config = dict(existing)
        if hasattr(self, "_ms"):
            self.contadores_global["fichas_restantes"] = max(0, int(self._ms.get_fichas_restantes()))
        base_config.update(
            {
                "promociones": self.promociones,
                "valor_ficha": self.valor_ficha,
                "device_id": codigo_hardware,
                "contadores_global": self.contadores_global,
                "contadores_parcial": self.contadores_parcial,
                "api": self.api_config,
                "admin": {"dni_admin": self.dni_admin},
                "atajos": {"promociones": self._normalizar_atajos_promociones(self.atajos_promociones)},
                "maquina": {
                    "codigo_hardware": codigo_hardware,
                    "tipo_maquina": 1,
                    "hoppers": self.maquina_hoppers,
                },
                "heartbeat": {"intervalo_s": self.heartbeat_intervalo_s},
                "operacion": self.operacion_config,
                "network_manager": self.network_manager_cfg,
            }
        )
        self.config_repository.save(base_config)

