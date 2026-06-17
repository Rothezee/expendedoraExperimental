"""Mixin GUI: administración (composición)."""

from expendedora.interface.gui.mixins.admin_shortcuts_mixin import AdminShortcutsMixin
from expendedora.interface.gui.mixins.admin_hardware_mixin import AdminHardwareMixin
from expendedora.interface.gui.mixins.admin_reports_mixin import AdminReportsMixin
from expendedora.interface.gui.mixins.admin_settings_mixin import AdminSettingsMixin


class AdminMixin(AdminShortcutsMixin, AdminHardwareMixin, AdminReportsMixin, AdminSettingsMixin):
    """Diálogos de administración."""
    pass
