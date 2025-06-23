# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import python modules
import os

# Import gtk modules - used for the config rows (optional, for future UI)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

class PullRequestsActions(ActionBase):
    """
    Example Action for PluginTemplate: PullRequests
    This action can be extended to fetch and display pull requests from a repository.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.github_token = ""
        self.refresh_rate = 60

    def on_ready(self) -> None:
        # Set an icon if available, otherwise skip
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "info.png")
        if os.path.exists(icon_path):
            self.set_media(media_path=icon_path, size=0.75)

    def on_key_down(self) -> None:
        print("PullRequests: Key down event triggered")
        # Placeholder for logic to fetch/display pull requests

    def on_key_up(self) -> None:
        print("PullRequests: Key up event triggered")
        # Placeholder for logic to clear or update UI

    def get_config_rows(self):
        # EntryRow for GitHub Access Token
        self.token_entry = Adw.EntryRow(
            title="GitHub Access Token"
        )
        self.token_entry.set_text(self.github_token)
        self.token_entry.connect("changed", self.on_token_changed)

        # ComboBoxText for Refresh Rate (dropdown with 0, 10, 30, 60; default 60)
        self.refresh_rate_row = Gtk.ComboBoxText()
        for rate in ["0", "10", "30", "60"]:
            self.refresh_rate_row.append_text(rate)
        self.refresh_rate_row.set_active(3)  # Default to "60"
        self.refresh_rate_row.connect("changed", self.on_refresh_rate_changed)

        # Return the widgets so they are shown in the UI
        return [self.token_entry, self.refresh_rate_row]

    def on_token_changed(self, entry):
        self.github_token = entry.get_text()

    def on_refresh_rate_changed(self, combo):
        text = combo.get_active_text()
        if text is not None:
            self.refresh_rate = int(text)
