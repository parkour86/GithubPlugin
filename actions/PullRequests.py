# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import python modules
import os
from loguru import logger as log
import requests

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
        self._refresh_timer_id = None  # For periodic refresh

    def on_ready(self) -> None:
        # Set an icon if available, otherwise skip
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "info.png")
        if os.path.exists(icon_path):
            self.set_media(media_path=icon_path, size=0.75)
        self.start_refresh_timer()

    def on_key_down(self) -> None:
        log.info("PullRequests: Key down event triggered")
        # Placeholder for logic to fetch/display pull requests

    def on_key_up(self) -> None:

        log.info("PullRequests: Key up event triggered")
        # Placeholder for logic to clear or update UI

    def get_config_rows(self):
        settings = self.get_settings()
        github_token = settings.get("github_token", "")
        repo_url = settings.get("repo_url", "")
        refresh_rate = settings.get("refresh_rate", "60")

        # Token entry
        token_entry = Adw.EntryRow(title="GitHub Access Token")
        token_entry.set_text(github_token)
        token_entry.connect("notify::text", self.on_token_changed)

        # Repo URL entry
        repo_entry = Adw.EntryRow(title="Repository URL (e.g. https://github.com/owner/repo)")
        repo_entry.set_text(repo_url)
        repo_entry.connect("notify::text", self.on_repo_url_changed)

        # ComboRow for refresh rate
        refresh_options = ["0", "10", "30", "60"]
        refresh_rate_row = ComboRow(
            action_core=self,
            var_name="refresh_rate",
            default_value=str(refresh_rate),
            items=refresh_options,
            title="Refresh Rate (minutes)",
            on_change=self.on_refresh_rate_changed,
            auto_add=False
        )

        return [token_entry, repo_entry, refresh_rate_row.widget]

    def on_token_changed(self, entry, *args):
        settings = self.get_settings()
        settings["github_token"] = entry.get_text()
        self.set_settings(settings)
        log.warning(f"[DEBUG] github_token: {settings.get('github_token', '')}")
        log.warning(f"[DEBUG] repo_url: {settings.get('repo_url', '')}")
        owner, repo = self.parse_owner_repo(settings.get("repo_url", ""))
        log.warning(f"[DEBUG] owner: {owner}")
        log.warning(f"[DEBUG] repo: {repo}")
        self.fetch_and_display_pull_request_count()

    def on_repo_url_changed(self, entry, *args):
        settings = self.get_settings()
        settings["repo_url"] = entry.get_text()
        self.set_settings(settings)
        log.warning(f"[DEBUG] github_token: {settings.get('github_token', '')}")
        log.warning(f"[DEBUG] repo_url: {settings.get('repo_url', '')}")
        owner, repo = self.parse_owner_repo(settings.get("repo_url", ""))
        log.warning(f"[DEBUG] owner: {owner}")
        log.warning(f"[DEBUG] repo: {repo}")
        self.fetch_and_display_pull_request_count()

    def on_refresh_rate_changed(self, widget, value, old):
        settings = self.get_settings()
        # If value is a ComboRowItem, extract its value
        if hasattr(value, "get_value"):
            value = value.get_value()
        if value is not None:
            settings["refresh_rate"] = value
        self.set_settings(settings)
        self.start_refresh_timer()

    def fetch_and_display_pull_request_count(self):
        try:
            settings = self.get_settings()
            github_token = settings.get("github_token", "")
            repo_url = settings.get("repo_url", "")
            owner, repo = self.parse_owner_repo(repo_url)

            if not owner or not repo or not github_token:
                self.set_bottom_label("Missing repo info or token", color=[255, 100, 100])
                return

            url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
            headers = {
                "Authorization": f"token {github_token}",
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
                self.set_bottom_label("Request failed", color=[255, 100, 100])
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

        # Get refresh_rate from settings
        settings = self.get_settings()
        refresh_rate = settings.get("refresh_rate", "60")
        try:
            refresh_rate = int(refresh_rate)
        except Exception:
            refresh_rate = 60

        # Don't start if refresh_rate is 0 or less
        if not isinstance(refresh_rate, int) or refresh_rate <= 0:
            return

        def _timer_callback():
            try:
                self.fetch_and_display_pull_request_count()
            except Exception:
                pass  # Never crash the app
            return True  # Continue timer

        try:
            self._refresh_timer_id = GLib.timeout_add_seconds(refresh_rate * 60, _timer_callback)
        except Exception:
            self._refresh_timer_id = None

    def __del__(self):
        try:
            from gi.repository import GLib
            if self._refresh_timer_id is not None:
                GLib.source_remove(self._refresh_timer_id)
        except Exception:
            pass

    def parse_owner_repo(self, repo_url):
        import re
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/?", repo_url)
        if match:
            owner = match.group(1)
            repo = match.group(2).rstrip(".git")
            return owner, repo
        return "", ""
