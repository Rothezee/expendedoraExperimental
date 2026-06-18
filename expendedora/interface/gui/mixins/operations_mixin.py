"""Mixin GUI: operaciones de dispensado."""

from expendedora.interface.gui.constants import PROMO_DEBOUNCE_S
from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class OperationsMixin:
    def _leer_cantidad_desde_entry(self, entry) -> int | None:
        """None si el campo está vacío o el valor no es válido (ya muestra error)."""
        cantidad_str = entry.get()
        if not cantidad_str:
            return None
        try:
            cantidad = int(cantidad_str)
        except ValueError:
            messagebox.showerror("Error", "Ingrese un valor numérico válido.")
            entry.focus_set()
            return None
        if cantidad <= 0:
            messagebox.showerror("Error", "La cantidad debe ser mayor a 0.")
            entry.focus_set()
            return None
        return cantidad

    def _on_click_status_arduino(self, *, confirm: bool = True):
        try:
            if self.app.get_serial_status().get("connected"):
                return
            if confirm and not messagebox.askyesno(
                "Reconectar Arduino",
                "El Arduino no está conectado.\n¿Intentar reconexión ahora?",
            ):
                return
            ok = self.app.force_reconnect()
            self._update_arduino_connection_label()
            self.root.update_idletasks()
            if ok:
                messagebox.showinfo("Reconectar Arduino", "Conexión restablecida.")
            else:
                messagebox.showwarning(
                    "Reconectar Arduino",
                    "No se pudo reconectar. Verificá el cable USB y el puerto COM.",
                )
            self.actualizar_estado_operacion_ui()
        except Exception as exc:
            messagebox.showerror("Reconectar Arduino", f"Error al reconectar:\n{exc}")


    def vaciar_buffer_dispensa_gui(self):
        pendientes = int(self._ms.get_fichas_restantes())
        if pendientes <= 0:
            messagebox.showinfo(
                "Vaciar fichas pendientes",
                "No hay fichas pendientes en el buffer de dispensado.",
            )
            return
        messagebox.showwarning(
            "Vaciar fichas pendientes",
            f"Hay {pendientes} ficha(s) pendiente(s) en el buffer.\n\n"
            "Se anulará la venta en caja: el dinero completo de la carga/promo "
            "y las fichas que ya salieron (contadas al dispensar).\n\n"
            "Devolvé primero a la tolva las fichas que salieron antes de confirmar. "
            "Luego podés volver a expender. No devuelve billetes al cliente.",
        )
        if not messagebox.askyesno(
            "Confirmar vaciado",
            "¿Confirmás vaciar el buffer de dispensado?",
        ):
            return
        try:
            revert = self.app.vaciar_buffer()
            self._revert_pending_counter_attribution(revert)
            self._actualizar_fichas_restantes_label(0)
            self.actualizar_estado_operacion_ui()
            self._persistir_estado_critico("vaciar_buffer")
            messagebox.showinfo(
                "Vaciar fichas pendientes",
                "Venta anulada en caja. Devolvé las fichas a la tolva si aún no lo hiciste "
                "y volvé a expender cuando esté listo.",
            )
        except Exception as exc:
            messagebox.showerror("Vaciar fichas pendientes", f"No se pudo vaciar el buffer:\n{exc}")


    def _cargar_fichas_en_buffer(self, cantidad: int) -> int:
        """Encola add_fichas y aplica al buffer antes de persistir (evita race con GUI)."""
        self._ms.gui_to_core_queue.put({"type": "add_fichas", "cantidad": cantidad})
        self._ms.process_gui_commands()
        restantes = int(self._ms.get_fichas_restantes())
        if restantes > 0:
            # Reflejo inmediato al presionar Expender/Enter (sin esperar primer TOKEN).
            self._ms.set_motor_activo(True)
            self._ms.set_motor_direccion("adelante")
        self._actualizar_fichas_restantes_label(restantes)
        self.actualizar_estado_operacion_ui()
        return restantes


    def procesar_expender_fichas(self):
        cantidad_fichas = self._leer_cantidad_desde_entry(self.entry_fichas)
        if cantidad_fichas is None:
            if not self.entry_fichas.get():
                self.entry_fichas.focus_set()
            return

        try:
            # Cargar en buffer de inmediato (no optimista: evita persistir 0)
            self._cargar_fichas_en_buffer(cantidad_fichas)

            # Dinero al inicio; fichas normales paso a paso (TOKEN)
            dinero = cantidad_fichas * self.valor_ficha
            self._increment_contador_operacion("dinero_ingresado", dinero)
            self._ms.register_pending_lot(
                cantidad_fichas,
                dinero_ingresado=dinero,
                fichas_normales=cantidad_fichas,
            )

            self._ms.set_r_cuenta(self.contadores_parcial["dinero_ingresado"], immediate=False)

            self._persistir_estado_critico("expender_fichas")
            self.contadores_labels["dinero_ingresado"].config(text=f"${self.contadores['dinero_ingresado']:.2f}")
            
            # Limpiar el campo de entrada
            self.entry_fichas.delete(0, tk.END)
            
            # **SOLUCIÓN LINUX**: Devolver foco explícitamente al entry
            # Esto mantiene los bindings activos sin necesidad de clic
            self.entry_fichas.focus_set()
            
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo expender fichas:\n{exc}")
            self.entry_fichas.focus_set()


    def procesar_devolucion_fichas(self):
        cantidad_fichas = self._leer_cantidad_desde_entry(self.entry_devolucion)
        if cantidad_fichas is None:
            if not self.entry_devolucion.get():
                self.entry_devolucion.focus_set()
            return

        try:
            self._cargar_fichas_en_buffer(cantidad_fichas)

            self._ms.register_pending_lot(
                cantidad_fichas,
                fichas_devolucion=cantidad_fichas,
            )

            self._persistir_estado_critico("devolucion_fichas")
            
            if "fichas_devolucion" in self.contadores_labels:
                self.contadores_labels["fichas_devolucion"].config(text=f"{self.contadores['fichas_devolucion']}")

            self.entry_devolucion.delete(0, tk.END)
            
            # **CAMBIO CRÍTICO**: Mostrar mensaje DESPUÉS de restaurar el foco
            # O mejor aún: usar un label de notificación en vez de messagebox
            self.entry_devolucion.focus_set()
            
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo procesar devolución:\n{exc}")
            self.entry_devolucion.focus_set()


    def procesar_cambio_fichas(self):
        cantidad_fichas = self._leer_cantidad_desde_entry(self.entry_cambio)
        if cantidad_fichas is None:
            if not self.entry_cambio.get():
                self.entry_cambio.focus_set()
            return

        try:
            self._cargar_fichas_en_buffer(cantidad_fichas)

            self._ms.register_pending_lot(
                cantidad_fichas,
                fichas_cambio=cantidad_fichas,
            )

            self._persistir_estado_critico("cambio_fichas")
            
            if "fichas_cambio" in self.contadores_labels:
                self.contadores_labels["fichas_cambio"].config(text=f"{self.contadores['fichas_cambio']}")

            self.entry_cambio.delete(0, tk.END)
            self.entry_cambio.focus_set()
            
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo procesar cambio:\n{exc}")
            self.entry_cambio.focus_set()


    def expender_fichas_gui(self):
        """Ya no es necesaria - el hardware controla todo automáticamente"""
        pass


    def simular_billetero(self):
        messagebox.showinfo("Simulación", "Billetero activado: Se ha ingresado dinero.")


    def simular_barrera(self):
        messagebox.showinfo("Simulación", "Barrera activada: Se detectó una ficha.")


    def simular_entrega_fichas(self):
        self.simular_salida_fichas()
        

    def simular_salida_fichas(self):
        """Simula un pulso de sensor (MCU o fallback local si no hay serial)."""
        try:
            if self.app.simulate_sensor_pulse():
                return
            messagebox.showwarning(
                "Simulación",
                "No hay fichas pendientes. Cargá fichas con Expender antes de simular.",
            )
        except Exception as exc:
            messagebox.showerror("Simulación", f"No se pudo simular la salida:\n{exc}")
            

    def _promo_fichas_configuradas(self, promo: str) -> int:
        raw = (self.promociones.get(promo) or {}).get("fichas", 0)
        try:
            return max(0, int(float(raw)))
        except (TypeError, ValueError):
            return 0

    def _promo_rebote_activo(self, promo: str) -> bool:
        """Evita disparos múltiples por autorepetición de tecla o doble bind."""
        now = time.time()
        last = float(getattr(self, "_promo_last_trigger_ts", {}).get(promo, 0.0))
        if now - last < PROMO_DEBOUNCE_S:
            print(f"[PROMO] Rebote ignorado {promo!r} (dt={now - last:.2f}s)")
            return True
        if not hasattr(self, "_promo_last_trigger_ts"):
            self._promo_last_trigger_ts = {}
        self._promo_last_trigger_ts[promo] = now
        return False

    def simular_promo(self, promo):
        if self._promo_rebote_activo(promo):
            return

        fichas = self._promo_fichas_configuradas(promo)
        if fichas <= 0:
            messagebox.showerror("Promoción", f"{promo} no tiene fichas configuradas (valor=0).")
            return

        pending_before = int(self._ms.get_fichas_restantes())

        promo_num = int(promo.split()[1])
        self._ms.gui_to_core_queue.put({"type": "promo", "promo_num": promo_num, "fichas": fichas})
        self._ms.process_gui_commands()
        pending_after = int(self._ms.get_fichas_restantes())
        print(
            f"[PROMO] {promo}: config_fichas={fichas} "
            f"buffer {pending_before} -> {pending_after}"
        )

        self._actualizar_fichas_restantes_label(pending_after)

        if pending_after > 0:
            self._ms.set_motor_activo(True)
            self._ms.set_motor_direccion("adelante")

        # Dinero y contador promo al inicio; fichas promoción paso a paso (TOKEN)
        precio = float((self.promociones.get(promo) or {}).get("precio", 0) or 0)
        self._increment_contador_operacion("dinero_ingresado", precio)

        self.contadores_labels["dinero_ingresado"].config(text=f"${self.contadores['dinero_ingresado']:.2f}")

        # Telemetría y core usan r_cuenta de sesión
        self._ms.set_r_cuenta(self.contadores_parcial["dinero_ingresado"], immediate=False)

        promo_key = PROMO_CONTADOR_KEYS.get(promo)
        lot_kwargs = {
            "dinero_ingresado": precio,
            "fichas_promocion": fichas,
        }
        if promo_key:
            self._increment_contador_operacion(promo_key, 1)
            lot_kwargs[promo_key] = 1
            self.contadores_labels[promo_key].config(text=f"{self.contadores[promo_key]}")
        else:
            messagebox.showerror("Error", "Promoción no válida.")
            return

        self._ms.register_pending_lot(fichas, **lot_kwargs)

        self.actualizar_contadores_gui()
        self._persistir_estado_critico("promo")
        
