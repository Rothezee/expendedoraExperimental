"""Mixin GUI: red y conectividad."""

from expendedora.interface.gui.mixins._comunes import *  # noqa: F403


class NetworkMixin:
    def _api_timeout_s(self) -> int:
        try:
            return max(1, int(float(self.api_config.get("timeout_s", 5))))
        except (TypeError, ValueError):
            return 5


    def _api_headers(self) -> dict:
        raw_headers = self.api_config.get("headers", {})
        if not isinstance(raw_headers, dict):
            raw_headers = {}
        headers = {}
        for key, value in raw_headers.items():
            key_str = str(key).strip()
            value_str = str(value).strip()
            if key_str and value_str:
                headers[key_str] = value_str
        headers.setdefault("User-Agent", "ExpendedoraGUI/1.0")
        return headers


    def _iter_backend_targets(self, local_path: str, cloud_path: str):
        base_urls = self.api_config.get("base_urls", [DNSLocal.rstrip("/"), DNS.rstrip("/")])
        if isinstance(base_urls, str):
            base_urls = [base_urls]
        if not isinstance(base_urls, list) or not base_urls:
            base_urls = [DNSLocal.rstrip("/"), DNS.rstrip("/")]
        for base in base_urls:
            normalized_base = str(base or "").strip().rstrip("/")
            if not normalized_base:
                continue
            endpoint = local_path if self._is_local_base_url(normalized_base) else cloud_path
            endpoint = str(endpoint or "").strip().lstrip("/")
            if not endpoint:
                continue
            scope = "local" if self._is_local_base_url(normalized_base) else "remoto"
            yield f"{normalized_base}/{endpoint}", scope


    def _post_backend_event(
        self,
        *,
        local_path: str,
        cloud_path: str,
        payload: dict,
        descripcion: str,
        retry_without_cashier_id: bool = False,
    ) -> None:
        self.app.post_backend_event(
            local_path=local_path,
            cloud_path=cloud_path,
            payload=payload,
            descripcion=descripcion,
            retry_without_cashier_id=retry_without_cashier_id,
        )


    def _init_update_toast(self):
        toast = tk.Frame(self.root, bg="#1F2A36", bd=0, relief="flat")
        toast.place_forget()

        title = tk.Label(
            toast,
            text="Actualización disponible",
            bg="#1F2A36",
            fg="white",
            font=("Segoe UI", 10, "bold"),
        )
        title.pack(anchor="w", padx=12, pady=(10, 2))

        subtitle = tk.Label(
            toast,
            text="Hay cambios nuevos. ¿Querés actualizar ahora?",
            bg="#1F2A36",
            fg="#D5DBDB",
            font=("Segoe UI", 9),
            wraplength=260,
            justify="left",
        )
        subtitle.pack(anchor="w", padx=12, pady=(0, 10))

        btn_row = tk.Frame(toast, bg="#1F2A36")
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        def _later():
            # “Luego”: ocultar y no molestar por 15 min
            self._update_snooze_until_ts = time.time() + (15 * 60)
            self._hide_update_toast()

        def _now():
            self._hide_update_toast()
            self._run_update_now()

        tk.Button(
            btn_row,
            text="Actualizar ahora",
            command=_now,
            bg="#2ECC71",
            fg="white",
            activebackground="#27AE60",
            activeforeground="white",
            bd=0,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        ).pack(side="left")
        tk.Button(
            btn_row,
            text="Luego",
            command=_later,
            bg="#566573",
            fg="white",
            activebackground="#4D5B66",
            activeforeground="white",
            bd=0,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        ).pack(side="left", padx=(8, 0))

        self._update_toast = toast


    def _show_update_toast(self):
        if not self._update_toast or self._update_toast_visible:
            return
        # Abajo izquierda con margen (por encima del footer)
        try:
            self._update_toast.place(x=14, rely=1.0, y=-(30 + 14), anchor="sw")
            self._update_toast.lift()
            self._update_toast_visible = True
        except Exception:
            pass


    def _hide_update_toast(self):
        if not self._update_toast or not self._update_toast_visible:
            return
        try:
            self._update_toast.place_forget()
        finally:
            self._update_toast_visible = False


    def _check_updates_async(self):
        if self._update_check_running:
            return
        if time.time() < self._update_snooze_until_ts:
            return
        self._update_check_running = True

        def _worker():
            try:
                cfg = self.config_repository.load()
                settings = cfg.get("updater", {}) if isinstance(cfg.get("updater", {}), dict) else {}
                remote = str(settings.get("remote", "origin"))
                branch = str(settings.get("branch", "main"))
                enabled = bool(settings.get("enabled", False))
                if not enabled:
                    return {"available": False}

                # fetch + compare hashes
                subprocess.run(
                    ["git", "fetch", remote, branch],
                    cwd=str(self._repo_root),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(self._repo_root), text=True).strip()
                remote_hash = subprocess.check_output(
                    ["git", "rev-parse", f"{remote}/{branch}"],
                    cwd=str(self._repo_root),
                    text=True,
                ).strip()
                return {"available": local != remote_hash, "remote_hash": remote_hash}
            except Exception:
                return {"available": False}

        def _done(result):
            try:
                self._update_last_remote_hash = result.get("remote_hash")
                if result.get("available"):
                    self._show_update_toast()
                else:
                    self._hide_update_toast()
            finally:
                self._update_check_running = False

        def _run_and_callback():
            res = _worker()
            self.root.after(0, lambda: _done(res))

        threading.Thread(target=_run_and_callback, daemon=True).start()


    def _run_update_now(self):
        # Ejecuta updater y fuerza reinicio de la app (kiosk la vuelve a levantar)
        def _worker():
            try:
                cmd = [self._python_executable(), str(self._repo_root / "updater" / "auto_updater.py"), "--once"]
                subprocess.run(cmd, cwd=str(self._repo_root), check=False)
            except Exception as exc:
                print(f"[UPDATER UI] Error al actualizar: {exc}")
                return
            try:
                # Salir para que el launcher kiosk reinicie con el nuevo código
                self.root.after(0, self.root.destroy)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()


    def _build_backend_probe_url(self):
        base_urls = self.api_config.get("base_urls", []) if isinstance(self.api_config, dict) else []
        if not isinstance(base_urls, list) or not base_urls:
            return "https://maquinasbonus.com/"
        base = str(base_urls[0]).rstrip("/")
        return f"{base}/"


    def _on_network_status_changed(self, status):
        if not isinstance(status, dict):
            return
        self._network_status_ui = status
        self._enqueue_gui_event("network", dict(status))


    def actualizar_estado_red_ui(self, status=None):
        if status is None:
            status = self._network_status_ui if isinstance(self._network_status_ui, dict) else {}
        level = str(status.get("level", "UNKNOWN")).upper()
        message = str(status.get("message", "") or "").strip()
        conn_name = str(status.get("active_connection", "") or "").strip()
        signal = status.get("signal_percent")
        internet_ok = bool(status.get("internet_ok"))
        backend_ok = bool(status.get("backend_ok"))
        signal_text = f" {int(signal)}%" if isinstance(signal, (int, float)) else ""
        conn_text = f" {conn_name}" if conn_name else ""
        net_badges = []
        net_badges.append("INT:OK" if internet_ok else "INT:--")
        net_badges.append("API:OK" if backend_ok else "API:--")
        label_text = f"Red: {level}{conn_text}{signal_text} {' '.join(net_badges)}"
        if message and not conn_name:
            label_text = f"Red: {level} ({message})"

        # En pantallas chicas (kiosk) acortar para que no se recorte:
        # priorizamos nivel + señal, luego nombre de conexión.
        max_len = 32
        if len(label_text) > max_len:
            compact = f"Red: {level}{signal_text}"
            if message and level in ("OFFLINE", "DEGRADED", "DISABLED") and len(compact) < (max_len - 3):
                compact = f"{compact} ({message})"
            label_text = compact[:max_len]

        if level == "ONLINE":
            bg, fg = "#27AE60", "white"
        elif level == "DEGRADED":
            bg, fg = "#F39C12", "white"
        elif level == "OFFLINE":
            bg, fg = "#C0392B", "white"
        elif level == "DISABLED":
            bg, fg = "#7F8C8D", "white"
        else:
            bg, fg = "#D6EAF8", "#1B4F72"
        self.status_network_lbl.config(text=label_text, bg=bg, fg=fg)

