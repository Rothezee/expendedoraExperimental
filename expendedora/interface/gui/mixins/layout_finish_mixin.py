"""Mixin GUI: footer, atajos y arranque final del layout."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class LayoutFinishMixin:
    def _finalize_layout(self, root, username):
                # --- Toast update (abajo izquierda) ---
                self._repo_root = Path(__file__).resolve().parent
                self._update_toast = None
                self._update_toast_visible = False
                self._update_check_running = False
                self._update_snooze_until_ts = 0.0
                self._update_last_check_ts = 0.0
                self._update_last_remote_hash = None
                self._init_update_toast()

                self.actualizar_fecha_hora()

                # --- ATAJOS DE TECLADO ---
                trigger_action = self._trigger_action

                # --- Configuración Global (Root) ---

                # Navegación global básica (si el foco se pierde)
                self.root.bind('<Up>', lambda e: self.entry_fichas.focus_set())
                self.root.bind('<KP_Up>', lambda e: self.entry_fichas.focus_set())

                self.root.bind('<Down>', lambda e: self.entry_cambio.focus_set())
                self.root.bind('<KP_Down>', lambda e: self.entry_cambio.focus_set())

                # Selección de tolva con flechas laterales
                self.root.bind('<Left>', lambda e: trigger_action(self.seleccionar_tolva_anterior))
                self.root.bind('<Right>', lambda e: trigger_action(self.seleccionar_tolva_siguiente))
                self.root.bind('<KP_Left>', lambda e: trigger_action(self.seleccionar_tolva_anterior))
                self.root.bind('<KP_Right>', lambda e: trigger_action(self.seleccionar_tolva_siguiente))

                self.aplicar_atajos_promos_root()

                # --- Configuración de Inputs (Bloquear teclas especiales) ---
                def configurar_input_atajos(entry):
                    """Configura los atajos para un Entry y bloquea escritura de caracteres especiales"""
            
                    # Navegación entre inputs con flechas
                    if entry == self.entry_fichas:
                        entry.bind('<Down>', lambda e: trigger_action(self.entry_devolucion.focus_set))
                        entry.bind('<KP_Down>', lambda e: trigger_action(self.entry_devolucion.focus_set))
                    elif entry == self.entry_devolucion:
                        entry.bind('<Up>', lambda e: trigger_action(self.entry_fichas.focus_set))
                        entry.bind('<KP_Up>', lambda e: trigger_action(self.entry_fichas.focus_set))
                        entry.bind('<Down>', lambda e: trigger_action(self.entry_cambio.focus_set))
                        entry.bind('<KP_Down>', lambda e: trigger_action(self.entry_cambio.focus_set))
                    elif entry == self.entry_cambio:
                        entry.bind('<Up>', lambda e: trigger_action(self.entry_devolucion.focus_set))
                        entry.bind('<KP_Up>', lambda e: trigger_action(self.entry_devolucion.focus_set))
                        # Down en el último podría ir al primero o nada
                        entry.bind('<Down>', lambda e: trigger_action(self.entry_fichas.focus_set)) # Loop al inicio

                    # Promos (bloquea escritura y dispara acción según config admin)
                    self.aplicar_atajos_promos_entry(entry)

                    # Enter para confirmar (detectar qué campo está activo)
                    def on_enter(event):
                        if event.widget == self.entry_fichas:
                            self.procesar_expender_fichas()
                        elif event.widget == self.entry_devolucion:
                            self.procesar_devolucion_fichas()
                        elif event.widget == self.entry_cambio:
                            self.procesar_cambio_fichas()
                        return "break"
            
                    entry.bind('<Return>', on_enter)
                    entry.bind('<KP_Enter>', on_enter)
            
                    # IMPORTANTE: Permitir navegación lateral con flechas izquierda/derecha
                    # (No bloquear estas para edición de texto)
                    # Left y Right se dejan sin bind para que funcionen normalmente

                # Aplicar configuración a ambos inputs
                configurar_input_atajos(self.entry_fichas)
                configurar_input_atajos(self.entry_devolucion)
                configurar_input_atajos(self.entry_cambio)
                self._entries_operativos = [self.entry_fichas, self.entry_devolucion, self.entry_cambio]
                self.asegurar_apertura_automatica_del_dia()
                self.actualizar_tolvas_gui()
                self.actualizar_estado_operacion_ui()
                self.actualizar_estado_red_ui(
                    {
                        "level": "UNKNOWN",
                        "message": "Inicializando red",
                        "active_connection": "",
                        "signal_percent": None,
                    }
                )
                self.network_service.start(callback=self._on_network_status_changed)
                self._startup_kiosk_mapped = False

                def _on_root_mapped(_event=None):
                    if self._startup_kiosk_mapped:
                        return
                    self._startup_kiosk_mapped = True
                    self.root.after(30, lambda: self.mostrar_frame(self.main_frame))

                self.root.bind('<Map>', _on_root_mapped, add='+')

                self.mostrar_frame(self.main_frame)
                self.root.after(1, lambda: self.mostrar_frame(self.main_frame))
                self.root.after(220, lambda: self.mostrar_frame(self.main_frame))
                # Evita que el primer toque se consuma solo en tomar foco de ventana.
                self.root.after(120, lambda: self.root.focus_force())

                # Tras login: NO resetear sesión aquí (logout lo hace en cerrar_sesion).
                # Preserva contadores ante reinicio imprevisto de la app.
                print(f"[GUI] Sesión iniciada para usuario: {username}")

