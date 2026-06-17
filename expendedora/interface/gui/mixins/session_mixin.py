"""Mixin GUI: sesión y cierres."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class SessionMixin:
    def _log_cierre_payload(self, tipo: str, payload: dict) -> None:
        usuario = str(getattr(self, "username", "") or "")
        cashier_id = getattr(self, "cashier_id", None)
        dinero = payload.get("dinero_ingresado", payload.get("dinero", payload.get("partial_dinero", 0)))
        fichas = payload.get("fichas_expendidas", payload.get("fichas_totales", payload.get("partial_fichas", 0)))
        tipo_evt = payload.get("tipo_evento", tipo)
        print(
            f"[CIERRE] {tipo} usuario={usuario!r} cashier_id={cashier_id} "
            f"tipo_evento={tipo_evt} fichas={fichas} dinero={dinero} "
            f"payload_cajero={payload.get('usuario_cajero')} id_cajero={payload.get('id_cajero', '-')}"
        )

    def asegurar_apertura_automatica_del_dia(self):
        """
        Ejecuta apertura automática una sola vez por día al primer login.
        Evita depender de un botón manual y deja registro en backend.
        """
        hoy = datetime.now().strftime("%Y-%m-%d")
        ultima_apertura = str(self.operacion_config.get("ultima_apertura_fecha", "") or "").strip()
        if ultima_apertura == hoy:
            return

        print(f"[GUI] Primera sesión del día ({hoy}) -> apertura automática")

        # Nuevo ciclo diario
        self.contadores_global = self.counter_service.default_counters()
        self.contadores_parcial = self.counter_service.default_counters()
        self._sync_counter_aliases()

        # Ajustar bases para mantener consistencia con contador hardware acumulado
        hw_actual = max(0, int(self._ms.get_fichas_sesion()))
        self.inicio_apertura_fichas = -hw_actual
        self.inicio_parcial_fichas = -hw_actual
        self._recalcular_bases_contadores()

        apertura_info = self.session_service.build_daily_close(
            self.device_id,
            self.contadores_global,
            event_type="apertura",
        )
        self._log_cierre_payload("apertura_auto", apertura_info)
        self._post_backend_event(
            local_path=urlCierresLocal,
            cloud_path=urlCierresCloud,
            payload=apertura_info,
            descripcion="Apertura automática",
        )

        self.operacion_config["ultima_apertura_fecha"] = hoy
        self.actualizar_contadores_gui()
        self._persistir_estado_critico("apertura")


    def realizar_apertura(self):
        # Inicia la apertura del día
        # Insertar cierre inicial con todo en 0 para registrar el día
        cierre_inicial = self.session_service.build_daily_close(
            self.device_id,
            self.contadores_global,
            event_type="apertura",
        )
        
        # Enviar cierre inicial al servidor remoto y local (no bloquea la GUI)
        self._post_backend_event(
            local_path=urlCierresLocal,
            cloud_path=urlCierresCloud,
            payload=cierre_inicial,
            descripcion="Apertura",
        )

        self.operacion_config["ultima_apertura_fecha"] = datetime.now().strftime("%Y-%m-%d")
        
        self.actualizar_contadores_gui()
        self._persistir_estado_critico("apertura_dia")
        messagebox.showinfo("Apertura", "Apertura del día realizada con éxito.\nRegistro inicial creado en el sistema.")


    def realizar_cierre(self):
        # Realiza el cierre del día
        cierre_info = self.session_service.build_daily_close(
            self.device_id,
            self.contadores_global,
            event_type="cierre",
        )
        self._log_cierre_payload("cierre_diario", cierre_info)
        mensaje_cierre = (
            f"Fichas expendidas: {cierre_info['fichas_expendidas']}\n"
            f"Dinero ingresado: ${cierre_info['dinero_ingresado']:.2f}\n"
            f"Promo 1 usadas: {cierre_info['promo1_contador']}\n"
            f"Promo 2 usadas: {cierre_info['promo2_contador']}\n"
            f"Promo 3 usadas: {cierre_info['promo3_contador']}\n"
            f"--- Desglose ---\n"
            f"Vendidas: {cierre_info['fichas_normales']} | Promoción: {cierre_info['fichas_promocion']} | Devolución: {cierre_info['fichas_devolucion']} | Cambio: {cierre_info['fichas_cambio']}"
        )
        messagebox.showinfo("Cierre", f"Cierre del día realizado:\n{mensaje_cierre}")
        
        # Enviar datos al servidor (no bloquea la GUI)
        self._post_backend_event(
            local_path=urlCierresLocal,
            cloud_path=urlCierresCloud,
            payload=cierre_info,
            descripcion="Cierre",
        )

        # Resetear solo acumulado global (cierre diario). La sesión del cajero
        # se mantiene hasta Cerrar sesión para GUI y subcierre de caja.
        self.contadores_global = self.counter_service.default_counters()
        self._sync_counter_aliases()

        hw_actual = max(0, int(self._ms.get_fichas_sesion()))
        self.inicio_apertura_fichas = -hw_actual
        self._recalcular_bases_contadores()
        self._persistir_estado_critico("cierre_dia")


    def realizar_cierre_parcial(self):
        # Realiza el cierre parcial
        subcierre_info = self.session_service.build_partial_close(
            self.device_id,
            self.contadores_parcial,
            self.username,
            cashier_id=self.cashier_id,
        )
        self._log_cierre_payload("cierre_parcial", subcierre_info)

        mensaje_subcierre = (
            f"Fichas expendidas: {subcierre_info['partial_fichas']}\n"
            f"Dinero ingresado: ${subcierre_info['partial_dinero']:.2f}\n"
            f"Promo 1 usadas: {subcierre_info['partial_p1']}\n"
            f"Promo 2 usadas: {subcierre_info['partial_p2']}\n"
            f"Promo 3 usadas: {subcierre_info['partial_p3']}\n"
            f"Devoluciones: {subcierre_info['partial_devolucion']}\n"
            f"Cambio: {subcierre_info['partial_cambio']}"
        )
        messagebox.showinfo("Cierre Parcial", f"Cierre parcial realizado:\n{mensaje_subcierre}")

        # Enviar datos al servidor (no bloquea la GUI)
        self._post_backend_event(
            local_path=urlSubcierreLocal,
            cloud_path=urlSubcierreCloud,
            payload=subcierre_info,
            descripcion="Subcierre",
            retry_without_cashier_id=True,
        )

        # Reiniciar los contadores parciales
        self.contadores_parcial = self.counter_service.default_counters()
        self._sync_counter_aliases()
        
        # Ajustar base parcial
        hw_actual = max(0, int(self._ms.get_fichas_sesion()))
        self.inicio_parcial_fichas = -hw_actual
        self._recalcular_bases_contadores()
        self._persistir_estado_critico("cierre_parcial")

    def cerrar_sesion(self):
        try:
            # Subcierre de caja: reporta la sesión actual del cajero, incluso si
            # ya se hizo el cierre diario (contadores parciales se conservan hasta aquí).
            contadores_a_enviar = self.contadores_parcial
            print("[GUI] Usando contadores parciales actuales para subcierre")

            # Best-effort: no bloquear logout si falla remoto/local.
            try:
                subcierre_info = self.session_service.build_partial_close(
                    self.device_id,
                    contadores_a_enviar,
                    self.username,
                    cashier_id=self.cashier_id,
                )
                self._log_cierre_payload("cerrar_sesion", subcierre_info)
                self._post_backend_event(
                    local_path=urlSubcierreLocal,
                    cloud_path=urlSubcierreCloud,
                    payload=subcierre_info,
                    descripcion="Cierre sesion",
                    retry_without_cashier_id=True,
                )
            except Exception as exc:
                print(f"[GUI] Aviso: no se pudo generar/enviar subcierre en logout: {exc}")

            self.contadores_parcial = self.counter_service.default_counters()
            self._sync_counter_aliases()
            try:
                self._ms.reset_fichas_sesion()
                self._ms.set_r_cuenta(0)
                self._ms.set_cuenta(0)
                # Mantener global acumulado entre sesiones de cajero.
                self.inicio_apertura_fichas = int(self.contadores_global.get("fichas_expendidas", 0))
                # Reiniciar solo la base parcial para la nueva sesión.
                self.inicio_parcial_fichas = 0
            except Exception as exc:
                print(f"[GUI] Aviso reseteando buffer de sesión: {exc}")
            try:
                self.actualizar_contadores_gui()
                self._persistir_estado_critico("cerrar_sesion")
            except Exception as exc:
                print(f"[GUI] Aviso guardando estado de sesión: {exc}")

            messagebox.showinfo("Cerrar Sesión", "La sesión ha sido cerrada.")
        finally:
            if callable(self.on_logout):
                try:
                    self.on_logout()
                except Exception as exc:
                    print(f"[GUI] on_logout callback error: {exc}")
            self._shutdown_ui(destroy_root=True)

