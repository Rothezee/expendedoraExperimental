"""Mixin GUI: administración — reportes BD."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class AdminReportsMixin:
    def abrir_reportes_admin(self):
        if not self._is_admin_user():
            messagebox.showerror("Permiso denegado", "Solo administrador puede ver reportes de BD.")
            return

        panel = tk.Toplevel(self.root)
        panel.title("Reportes y cierres (BD)")
        panel.geometry("1180x640")
        panel.configure(bg="#ffffff")
        panel.transient(self.root)
        self._set_modal_grab(panel)

        toolbar = tk.Frame(panel, bg="#ffffff")
        toolbar.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(toolbar, text="ID dispositivo", bg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        device_var = tk.StringVar(value=self.device_id)
        tk.Entry(toolbar, textvariable=device_var, width=20, font=("Segoe UI", 9)).pack(side="left", padx=(6, 12))
        tk.Label(toolbar, text="Límite", bg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        limit_var = tk.StringVar(value="80")
        tk.Entry(toolbar, textvariable=limit_var, width=6, font=("Segoe UI", 9), justify="center").pack(side="left", padx=(6, 12))
        status_lbl = tk.Label(toolbar, text="", bg="#ffffff", fg="#7F8C8D", font=("Segoe UI", 9, "bold"))
        status_lbl.pack(side="left", padx=(8, 0))

        notebook = ttk.Notebook(panel)
        notebook.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        daily_tab = tk.Frame(notebook, bg="#ffffff")
        partial_tab = tk.Frame(notebook, bg="#ffffff")
        telemetry_tab = tk.Frame(notebook, bg="#ffffff")
        summary_tab = tk.Frame(notebook, bg="#ffffff")
        notebook.add(daily_tab, text="Cierres diarios")
        notebook.add(partial_tab, text="Cierres parciales")
        notebook.add(telemetry_tab, text="Telemetría expendedora")
        notebook.add(summary_tab, text="Resumen reportes")

        daily_cols = ("id_cierre", "id_dispositivo", "fichas_totales", "dinero", "p1", "p2", "p3", "fichas_promo", "fecha_apertura", "tipo_evento")
        partial_cols = (
            "id_cierre_parcial",
            "id_dispositivo",
            "id_cajero",
            "fichas_totales",
            "dinero",
            "p1",
            "p2",
            "p3",
            "fichas_promo",
            "fichas_devolucion",
            "fichas_cambio",
            "fecha_apertura_turno",
        )
        telemetry_cols = ("id_lectura", "id_dispositivo", "fichas", "dinero", "fecha_registro")
        daily_tree = ttk.Treeview(daily_tab, columns=daily_cols, show="headings")
        partial_tree = ttk.Treeview(partial_tab, columns=partial_cols, show="headings")
        telemetry_tree = ttk.Treeview(telemetry_tab, columns=telemetry_cols, show="headings")
        summary_text = tk.Text(
            summary_tab,
            bg="#F8F9F9",
            fg="#2C3E50",
            font=("Consolas", 10),
            wrap="word",
            bd=1,
            relief="solid",
            padx=10,
            pady=10,
        )
        summary_text.pack(fill="both", expand=True, padx=8, pady=8)
        summary_text.insert("1.0", "Cargando resumen...")
        summary_text.config(state="disabled")

        for tree, columns in ((daily_tree, daily_cols), (partial_tree, partial_cols), (telemetry_tree, telemetry_cols)):
            for col in columns:
                tree.heading(col, text=col)
                width = 120
                if "fecha" in col:
                    width = 170
                elif col in ("id_dispositivo", "tipo_evento"):
                    width = 150
                tree.column(col, width=width, anchor="center")
            vsb = ttk.Scrollbar(tree.master, orient="vertical", command=tree.yview)
            hsb = ttk.Scrollbar(tree.master, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tree.pack(fill="both", expand=True, side="top")
            vsb.pack(side="right", fill="y")
            hsb.pack(side="bottom", fill="x")

        def fill_tree(tree, rows, columns):
            tree.delete(*tree.get_children())
            for row in rows:
                values = [row.get(col, "") for col in columns]
                tree.insert("", "end", values=values)

        def to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def to_int(value):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0

        def render_summary(daily_rows, partial_rows, telemetry_rows):
            total_daily = len(daily_rows)
            total_partial = len(partial_rows)
            total_telemetry = len(telemetry_rows)

            total_dinero_daily = sum(to_float(r.get("dinero")) for r in daily_rows)
            total_fichas_daily = sum(to_int(r.get("fichas_totales")) for r in daily_rows)
            total_promo_daily = sum(to_int(r.get("fichas_promo")) for r in daily_rows)

            total_dinero_partial = sum(to_float(r.get("dinero")) for r in partial_rows)
            total_fichas_partial = sum(to_int(r.get("fichas_totales")) for r in partial_rows)
            total_devolucion_partial = sum(to_int(r.get("fichas_devolucion")) for r in partial_rows)
            total_cambio_partial = sum(to_int(r.get("fichas_cambio")) for r in partial_rows)
            total_fichas_telemetry = sum(to_int(r.get("fichas")) for r in telemetry_rows)
            total_dinero_telemetry = sum(to_float(r.get("dinero")) for r in telemetry_rows)

            avg_daily = (total_dinero_daily / total_daily) if total_daily else 0.0
            avg_partial = (total_dinero_partial / total_partial) if total_partial else 0.0

            lines = [
                "RESUMEN DE REPORTES",
                "",
                f"- Registros diarios cargados: {total_daily}",
                f"- Registros parciales cargados: {total_partial}",
                f"- Lecturas telemetría cargadas: {total_telemetry}",
                "",
                "CIERRES DIARIOS",
                f"- Dinero total: ${total_dinero_daily:.2f}",
                f"- Fichas totales: {total_fichas_daily}",
                f"- Fichas promo: {total_promo_daily}",
                f"- Promedio dinero por cierre: ${avg_daily:.2f}",
                "",
                "CIERRES PARCIALES",
                f"- Dinero total: ${total_dinero_partial:.2f}",
                f"- Fichas totales: {total_fichas_partial}",
                f"- Fichas devolución: {total_devolucion_partial}",
                f"- Fichas cambio: {total_cambio_partial}",
                f"- Promedio dinero por subcierre: ${avg_partial:.2f}",
                "",
                "TELEMETRÍA EXPENDEDORA",
                f"- Dinero total telemetría: ${total_dinero_telemetry:.2f}",
                f"- Fichas total telemetría: {total_fichas_telemetry}",
                "",
                f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ]

            summary_text.config(state="normal")
            summary_text.delete("1.0", tk.END)
            summary_text.insert("1.0", "\n".join(lines))
            summary_text.config(state="disabled")

        def cargar():
            status_lbl.config(text="Consultando BD...", fg="#1F618D")
            try:
                limit = int(float(limit_var.get()))
            except ValueError:
                messagebox.showerror("Filtro inválido", "El límite debe ser numérico.")
                return
            device = device_var.get().strip()

            def worker():
                try:
                    daily_rows = self.report_repository.fetch_daily_closures(limit=limit, device_id=device)
                    partial_rows = self.report_repository.fetch_partial_closures(limit=limit, device_id=device)
                    telemetry_rows = self.report_repository.fetch_expendedora_telemetry(limit=limit, device_id=device)
                    self.root.after(
                        0,
                        lambda: (
                            fill_tree(daily_tree, daily_rows, daily_cols),
                            fill_tree(partial_tree, partial_rows, partial_cols),
                            fill_tree(telemetry_tree, telemetry_rows, telemetry_cols),
                            render_summary(daily_rows, partial_rows, telemetry_rows),
                            status_lbl.config(
                                text=(
                                    f"{len(daily_rows)} diarios | {len(partial_rows)} parciales | "
                                    f"{len(telemetry_rows)} telemetría"
                                ),
                                fg="#1E8449",
                            ),
                        ),
                    )
                except Exception as exc:
                    err_text = self.app.format_db_error(exc)
                    hint = (
                        " En config.json, sección \"mysql\": objetos \"local\" y \"production\" "
                        "(host, usuario, contraseña, database)."
                    )
                    self.root.after(
                        0,
                        lambda t=err_text, h=hint: status_lbl.config(
                            text=f"Error BD: {t}.{h}",
                            fg="#C0392B",
                        ),
                    )

            threading.Thread(target=worker, daemon=True).start()

        tk.Button(toolbar, text="Refrescar", command=cargar, bg="#3498DB", fg="white", font=("Segoe UI", 9, "bold"), bd=0, padx=12, pady=4).pack(side="right")
        cargar()
