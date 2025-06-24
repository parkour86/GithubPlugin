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

# Import ComboRow for dropdowns
from GtkHelper.GenerativeUI.ComboRow import ComboRow

class PullRequestsActions(ActionBase):
    """
    Example Action for PluginTemplate: PullRequests
    This action can be extended to fetch and display pull requests from a repository.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.github_token = ""
        self.repo_url = ""
        self.owner = ""
        self.repo = ""
        self.refresh_rate = 60
        self._refresh_timer_id = None  # For periodic refresh

    def on_ready(self) -> None:
        # Set an icon if available, otherwise skip
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "info.png")
        if os.path.exists(icon_path):
            self.set_media(media_path=icon_path, size=0.75)
        self.start_refresh_timer()

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

        # EntryRow for GitHub Repo URL
        self.repo_entry = Adw.EntryRow(
            title="Repository URL (e.g. https://github.com/owner/repo)"
        )
        self.repo_entry.set_text(self.repo_url)
        self.repo_entry.connect("changed", self.on_repo_url_changed)

        # ComboRow for Refresh Rate (dropdown with 0, 10, 30, 60; default 60)
        refresh_options = ["0", "10", "30", "60"]
        self.refresh_rate_row = ComboRow(
            action_core=self,
            var_name="refresh_rate",
            default_value=str(self.refresh_rate),
            items=refresh_options,
            title="Refresh Rate (minutes)",
            on_change=self.on_refresh_rate_changed
        )

        # Return the widgets so they are shown in the UI
        return [self.token_entry, self.repo_entry, self.refresh_rate_row.widget]

    def on_token_changed(self, entry):
        self.github_token = entry.get_text()
        self.fetch_and_display_pull_request_count()

    def on_repo_url_changed(self, entry):
        self.repo_url = entry.get_text()
        # Parse owner and repo from the URL
        # Example: https://github.com/owner/repo
        import re
        match = re.match(r"https?://github\\.com/([^/]+)/([^/]+)", self.repo_url)
        if match:
            self.owner = match.group(1)
            self.repo = match.group(2)
        else:
            self.owner = ""
            self.repo = ""
        self.fetch_and_display_pull_request_count()

    def on_refresh_rate_changed(self, widget, value, old):
        # value is the new selected value from ComboRow
        if value is not None:
            try:
                self.refresh_rate = int(value)
            except Exception:
                self.refresh_rate = 60
            self.start_refresh_timer()

    def fetch_and_display_pull_request_count(self):
        try:
            import requests
            if not self.owner or not self.repo or not self.github_token:
                self.set_bottom_label("Missing repo info or token", color=[255, 100, 100])
                return

            url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls"
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }

            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    pulls = response.json()
                    pr_count = len(pulls)
                    self.set_bottom_label(f"Open PRs: {pr_count}", color=[100, 255, 100])
                else:
                    self.set_bottom_label(f"Error: {response.status_code}", color=[255, 100, 100])
            except Exception:
                self.set_bottom_label(f"Request failed", color=[255, 100, 100])
        except Exception:
            self.set_bottom_label("Internal error", color=[255, 100, 100])

    def start_refresh_timer(self):
        try:
            from gi.repository import GLib
        except ImportError:
            return

        # Cancel any existing timer
        if self._refresh_timer_id is not None:
            try:
                GLib.source_remove(self._refresh_timer_id)
            except Exception:
                pass
            self._refresh_timer_id = None

        # Don't start if refresh_rate is 0 or less
        if not isinstance(self.refresh_rate, int) or self.refresh_rate <= 0:
            return

        def _timer_callback():
            try:
                self.fetch_and_display_pull_request_count()
            except Exception:
                pass  # Never crash the app
            return True  # Continue timer

        try:
            self._refresh_timer_id = GLib.timeout_add_seconds(self.refresh_rate * 60, _timer_callback)
        except Exception:
            self._refresh_timer_id = None

    def __del__(self):
        try:
            from gi.repository import GLib
            if self._refresh_timer_id is not None:
                GLib.source_remove(self._refresh_timer_id)
        except Exception:
            pass
