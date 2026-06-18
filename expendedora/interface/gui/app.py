from expendedora.interface.gui.mixins.admin_mixin import AdminMixin
from expendedora.interface.gui.mixins.config_mixin import ConfigMixin
from expendedora.interface.gui.mixins.help_mixin import HelpMixin
from expendedora.interface.gui.mixins.layout_mixin import LayoutMixin
from expendedora.interface.gui.mixins.network_mixin import NetworkMixin
from expendedora.interface.gui.mixins.operations_mixin import OperationsMixin
from expendedora.interface.gui.mixins.session_mixin import SessionMixin
from expendedora.interface.gui.mixins.shortcuts_mixin import ShortcutsMixin
from expendedora.interface.gui.mixins.tolvas_mixin import TolvasMixin
from expendedora.interface.gui.mixins.ui_mixin import UiMixin


class ExpendedoraGUI(
    LayoutMixin,
    NetworkMixin,
    ShortcutsMixin,
    TolvasMixin,
    ConfigMixin,
    AdminMixin,
    OperationsMixin,
    SessionMixin,
    UiMixin,
    HelpMixin,
):
    """GUI principal — compuesta por mixins de capa interfaz."""
