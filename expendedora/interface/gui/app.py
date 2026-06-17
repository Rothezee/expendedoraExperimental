import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
import os
import subprocess
import time
import json
from pathlib import Path
import requests
from expendedora.logic.application.bootstrap import create_app_controller
from expendedora.logic.application.app_controller import AppController, DEFAULT_DNI_ADMIN

from expendedora.interface.gui.constants import (
    DEFAULT_PROMO_HOTKEYS,
    DNS,
    DNS_LOCAL as DNSLocal,
    URL_CIERRES_CLOUD as urlCierresCloud,
    URL_CIERRES_LOCAL as urlCierresLocal,
    URL_SUBCIERRE_CLOUD as urlSubcierreCloud,
    URL_SUBCIERRE_LOCAL as urlSubcierreLocal,
)

import queue
import threading as _threading

def _post_en_hilo(url, datos, descripcion="", retry_without_cashier_id=False, timeout_s=5, headers=None):
    """
    Envía un POST HTTP en un hilo separado con timeout.
    Nunca bloquea el hilo de Tkinter aunque no haya internet.
    """
    def _enviar():
        try:
            req_headers = headers if isinstance(headers, dict) else {}
            resp = requests.post(url, json=datos, timeout=timeout_s, headers=req_headers)
            print(f"[NET] {descripcion} -> {resp.status_code}")
            body_preview = ""
            if resp.status_code >= 400:
                body_preview = str(resp.text or "").strip().replace("\n", " ")
                if len(body_preview) > 240:
                    body_preview = f"{body_preview[:240]}..."
                print(f"[NET WARN] {descripcion} body: {body_preview or '-'}")

            # Compatibilidad backend remoto: si id_cajero no coincide entre entornos
            # reintentamos usando usuario (employee_id/usuario_cajero) sin id numérico.
            if (
                retry_without_cashier_id
                and resp.status_code == 404
                and "cajero no encontrado" in (body_preview or "").lower()
                and isinstance(datos, dict)
                and "id_cajero" in datos
            ):
                retry_payload = dict(datos)
                retry_payload.pop("id_cajero", None)
                retry_desc = f"{descripcion} (retry sin id_cajero)"
                retry_resp = requests.post(url, json=retry_payload, timeout=timeout_s, headers=req_headers)
                print(f"[NET] {retry_desc} -> {retry_resp.status_code}")
                if retry_resp.status_code >= 400:
                    retry_body = str(retry_resp.text or "").strip().replace("\n", " ")
                    if len(retry_body) > 240:
                        retry_body = f"{retry_body[:240]}..."
                    print(f"[NET WARN] {retry_desc} body: {retry_body or '-'}")
        except requests.exceptions.RequestException as e:
            print(f"[NET ERROR] {descripcion}: {e}")
    _threading.Thread(target=_enviar, daemon=True).start()


from expendedora.interface.gui.mixins.help_mixin import HelpMixin
from expendedora.interface.gui.mixins.layout_mixin import LayoutMixin
from expendedora.interface.gui.mixins.network_mixin import NetworkMixin
from expendedora.interface.gui.mixins.shortcuts_mixin import ShortcutsMixin
from expendedora.interface.gui.mixins.tolvas_mixin import TolvasMixin
from expendedora.interface.gui.mixins.config_mixin import ConfigMixin
from expendedora.interface.gui.mixins.admin_mixin import AdminMixin
from expendedora.interface.gui.mixins.operations_mixin import OperationsMixin
from expendedora.interface.gui.mixins.session_mixin import SessionMixin
from expendedora.interface.gui.mixins.ui_mixin import UiMixin


class ExpendedoraGUI(LayoutMixin, NetworkMixin, ShortcutsMixin, TolvasMixin, ConfigMixin, AdminMixin, OperationsMixin, SessionMixin, UiMixin, HelpMixin):
    """GUI principal — compuesta por mixins de capa interfaz."""
    pass
