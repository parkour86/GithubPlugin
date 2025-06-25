# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import python modules
import os
from loguru import logger as log
import requests
from datetime import datetime
from PIL import Image, ImageDraw

# Import gtk modules - used for the config rows (optional, for future UI)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

# Import ComboRow for dropdowns
from GtkHelper.GenerativeUI.ComboRow import ComboRow

class ContributionsActions(ActionBase):
    WHITE_BG = [255, 255, 255, 255]  # Used to avoid repeating color

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._token_change_timeout_id = None
        self._user_change_timeout_id = None
        self._refresh_timer_id = None  # For periodic refresh

    def on_ready(self) -> None:
        settings = self.get_settings()
        github_token = settings.get("github_token", "")
        github_user = settings.get("github_user", "")
        if github_token and github_user:
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#595959.png"), size=0.9)
            self.fetch_and_display_contributions()
        else:
            self.clear_labels("error")
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "info.png"), size=0.9)
            self.set_top_label("\nConfigure\nGithub\nPlugin", color=[255, 100, 100], outline_width=1, font_size=17)
        self.start_refresh_timer()

    def on_key_down(self) -> None:
        settings = self.get_settings()
        github_user = settings.get("github_user", "")
        if github_user:
            import webbrowser
            url = f"https://github.com/{github_user}"
            webbrowser.open(url)
        else:
            log.warning("Contributions: Cannot open user page, username missing.")

    def on_key_up(self) -> None:
        log.info("Contributions: Key up event triggered")

    def get_config_rows(self):
        settings = self.get_settings()
        github_token = settings.get("github_token", "")
        github_user = settings.get("github_user", "")
        refresh_rate = settings.get("refresh_rate", "0")

        token_entry = Adw.EntryRow(title="GitHub Access Token")
        token_entry.set_text(github_token)
        token_entry.connect("notify::text", self.on_token_changed)

        user_entry = Adw.EntryRow(title="GitHub Username")
        user_entry.set_text(github_user)
        user_entry.connect("notify::text", self.on_user_changed)

        refresh_options = ["0", "1", "6", "12", "24", "48"]
        refresh_rate_row = ComboRow(
            action_core=self,
            var_name="refresh_rate",
            default_value=str(refresh_rate),
            items=refresh_options,
            title="Refresh Rate (hours)",
            on_change=self.on_refresh_rate_changed,
            auto_add=False
        )

        month_labels = None
        if getattr(self, "_quarter_labels", None) and getattr(self, "_quarter_images", None):
            month_labels = [
                label for label, img in zip(self._quarter_labels, self._quarter_images) if img is not None
            ]
        if not month_labels:
            bimonthly_ranges = self.get_bimonthly_ranges(datetime.now())
            month_labels = [f"{start.strftime('%b')}-{end.strftime('%b')}" for start, end in bimonthly_ranges]

        display_month_row = ComboRow(
            action_core=self,
            var_name="display_contribution_month",
            default_value="",
            items=month_labels,
            title="Display Contribution Period",
            on_change=self.on_display_month_changed,
            auto_add=False
        )

        show_top_label = settings.get("show_top_label", True)
        show_top_label_row = Adw.SwitchRow(title="Show/Hide Contribution Count")
        show_top_label_row.set_active(show_top_label)
        show_top_label_row.connect("notify::active", self.on_show_top_label_changed)

        show_bottom_label = settings.get("show_bottom_label", True)
        show_bottom_label_row = Adw.SwitchRow(title="Show/Hide Bottom Label")
        show_bottom_label_row.set_active(show_bottom_label)
        show_bottom_label_row.connect("notify::active", self.on_show_bottom_label_changed)

        return [
            token_entry,
            user_entry,
            refresh_rate_row.widget,
            display_month_row.widget,
            show_top_label_row,
            show_bottom_label_row,
        ]

    def on_token_changed(self, entry, *args):
        from gi.repository import GLib
        if self._token_change_timeout_id is not None:
            try:
                GLib.source_remove(self._token_change_timeout_id)
            except Exception:
                pass
            self._token_change_timeout_id = None

        def do_update():
            settings = self.get_settings()
            settings["github_token"] = entry.get_text()
            self.set_settings(settings)
            self.fetch_and_display_contributions()
            self._token_change_timeout_id = None
            return False

        self._token_change_timeout_id = GLib.timeout_add(500, do_update)

    def on_user_changed(self, entry, *args):
        from gi.repository import GLib
        if self._user_change_timeout_id is not None:
            try:
                GLib.source_remove(self._user_change_timeout_id)
            except Exception:
                pass
            self._user_change_timeout_id = None

        def do_update():
            settings = self.get_settings()
            settings["github_user"] = entry.get_text()
            self.set_settings(settings)
            self.fetch_and_display_contributions()
            self._user_change_timeout_id = None
            return False

        self._user_change_timeout_id = GLib.timeout_add(500, do_update)

    def on_refresh_rate_changed(self, widget, value, old):
        settings = self.get_settings()
        if hasattr(value, "get_value"):
            value = value.get_value()
        if value is not None:
            settings["refresh_rate"] = value
        self.set_settings(settings)
        self.start_refresh_timer()

    def clear_labels(self, status):
        self.set_top_label(None)
        self.set_center_label(None)
        self.set_bottom_label(None)
        if status == "success":
            self.set_background_color(color=[0, 0, 0, 0], update=True)
        elif status == "error":
            self.set_background_color(color=self.WHITE_BG, update=True)

    def on_show_top_label_changed(self, widget, *args):
        settings = self.get_settings()
        settings["show_top_label"] = widget.get_active()
        self.set_settings(settings)
        self.fetch_and_display_contributions()

    def on_show_bottom_label_changed(self, widget, *args):
        settings = self.get_settings()
        settings["show_bottom_label"] = widget.get_active()
        self.set_settings(settings)
        self.fetch_and_display_contributions()

    def on_display_month_changed(self, widget, value, old):
        settings = self.get_settings()
        selected_label = value.get_value() if hasattr(value, "get_value") else value
        if not isinstance(selected_label, str):
            log.warning("Invalid value for display month; skipping update.")
            return

        if getattr(self, "_quarter_labels", None) and getattr(self, "_quarter_images", None):
            filtered = [
                (label, img) for label, img in zip(self._quarter_labels, self._quarter_images) if img is not None
            ]
            filtered_labels = [label for label, img in filtered]
            filtered_images = [img for label, img in filtered]
            if selected_label in filtered_labels:
                idx = filtered_labels.index(selected_label)
                img_path = filtered_images[idx]
                if img_path:
                    self.set_media(media_path=img_path, size=0.49)

    def start_refresh_timer(self):
        try:
            from gi.repository import GLib
        except ImportError:
            return

        if self._refresh_timer_id is not None:
            try:
                GLib.source_remove(self._refresh_timer_id)
            except Exception:
                pass
            self._refresh_timer_id = None

        settings = self.get_settings()
        refresh_rate = settings.get("refresh_rate", "1")
        try:
            refresh_rate = int(refresh_rate)
        except Exception:
            refresh_rate = 1

        if not isinstance(refresh_rate, int) or refresh_rate <= 0:
            return

        def _timer_callback():
            try:
                self.fetch_and_display_contributions()
            except Exception as e:
                log.exception(f"[Contributions] Timer callback error: {e}")
            return True

        try:
            self._refresh_timer_id = GLib.timeout_add_seconds(refresh_rate * 3600, _timer_callback)
        except Exception:
            self._refresh_timer_id = None
