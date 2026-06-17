"""Imports compartidos por los mixins de la GUI."""

import json
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import requests

from expendedora.interface.gui.constants import (
    DEFAULT_PROMO_HOTKEYS,
    DNS,
    DNS_LOCAL as DNSLocal,
    URL_CIERRES_CLOUD as urlCierresCloud,
    URL_CIERRES_LOCAL as urlCierresLocal,
    URL_SUBCIERRE_CLOUD as urlSubcierreCloud,
    URL_SUBCIERRE_LOCAL as urlSubcierreLocal,
)
from expendedora.logic.application.app_controller import AppController, DEFAULT_DNI_ADMIN
from expendedora.logic.application.bootstrap import create_app_controller
