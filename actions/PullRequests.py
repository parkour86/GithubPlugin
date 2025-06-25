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
        settings = self.get_settings()
        github_token = settings.get("github_token", "")
        repo_url = settings.get("repo_url", "")
        if github_token and repo_url and repo_url.startswith("https://github.com/"):
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#595959.png"), size=0.9)
            self.fetch_and_display_pull_request_count()
        else:
            self.clear_labels("error")
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "info.png"), size=0.9)
            self.set_top_label("\nConfigure\nGithub\nPlugin", color=[255, 100, 100], outline_width=1, font_size=17)

        self.start_refresh_timer()

    def on_key_down(self) -> None:
        settings = self.get_settings()
        repo_url = settings.get("repo_url", "")
        owner, repo = self.parse_owner_repo(repo_url)
        if owner and repo:
            import webbrowser
            url = f"https://github.com/{owner}/{repo}/pulls"
            webbrowser.open(url)
        else:
            log.warning("PullRequests: Cannot open PRs page, owner or repo missing.")

    def on_key_up(self) -> None:

        log.info("PullRequests: Key up event triggered")
        # Placeholder for logic to clear or update UI

    def get_config_rows(self):
        settings = self.get_settings()
        github_token = settings.get("github_token", "")
        repo_url = settings.get("repo_url", "")
        refresh_rate = settings.get("refresh_rate", "0")

        # Token entry
        token_entry = Adw.EntryRow(title="GitHub Access Token")
        token_entry.set_text(github_token)
        token_entry.connect("notify::text", self.on_token_changed)

        # Repo URL entry
        repo_entry = Adw.EntryRow(title="Repository URL (e.g. https://github.com/&lt;owner&gt;/&lt;repo&gt;)")
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
        #owner, repo = self.parse_owner_repo(settings.get("repo_url", ""))
        self.fetch_and_display_pull_request_count()

    def on_repo_url_changed(self, entry, *args):
        settings = self.get_settings()
        settings["repo_url"] = entry.get_text()
        self.set_settings(settings)
        #owner, repo = self.parse_owner_repo(settings.get("repo_url", ""))
        self.fetch_and_display_pull_request_count()

    def parse_owner_repo(self, repo_url):
        import re
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/?", repo_url)
        if match:
            owner = match.group(1)
            repo = match.group(2).removesuffix(".git")
            return owner, repo
        return "", ""

    def on_refresh_rate_changed(self, widget, value, old):
        settings = self.get_settings()
        # If value is a ComboRowItem, extract its value
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
            self.set_background_color(color=[255, 255, 255, 255], update=True)

    def fetch_and_display_pull_request_count(self):
        # Common red label parameters
        red = [255, 100, 100]
        kwargs = {"color": red, "outline_width": 1, "font_size": 17, "font_family": "cantarell"}
        default_media = os.path.join(self.plugin_base.PATH, "assets", "info.png")

        try:
            settings = self.get_settings()
            github_token = settings.get("github_token", "")
            repo_url = settings.get("repo_url", "")
            owner, repo = self.parse_owner_repo(repo_url)
            log.info(f"[DEBUG] Fetching pull requests for {owner}/{repo}")

            if not owner or not repo or not github_token:
                self.clear_labels("error")
                self.set_background_color(color=[255, 255, 255, 255], update=True)
                self.set_top_label("\nConfigure\nGithub\nPlugin", **kwargs)
                self.set_media(media_path=default_media, size=0.9)
                #self.set_bottom_label("Missing Info", color=[255, 100, 100], outline_width=1, font_family="cantarell")
                return

            url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }

            try:
                response = requests.get(url, headers=headers, timeout=10)
                status = response.status_code

                if status == 200:
                    pulls = response.json()
                    pr_count = len(pulls)
                    self.clear_labels("success")
                    self.set_center_label("PRs", color=[100, 255, 100], outline_width=2, font_size=20, font_family="cantarell")
                    self.set_bottom_label(f"{pr_count}", color=[100, 255, 100], outline_width=4, font_size=20, font_family="cantarell")
                    # Set default gray Github icon
                    self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#595959.png"), size=0.9)
                    # Extract SHAs and check commit statuses only if there are PRs
                    if pr_count > 0:
                        shas = [pr["head"]["sha"] for pr in pulls if "head" in pr and "sha" in pr["head"]]
                        self.fetch_and_set_commit_status_icons(owner, repo, shas)
                else:
                    self.clear_labels("error")

                    if status == 404:
                        self.set_top_label("\nInvalid\nRepo URL", **kwargs)

                    elif status == 401:
                        self.set_top_label("\nInvalid\nToken", **kwargs)

                    else:
                        self.set_top_label("\nConfigure\nGithub\nPlugin", **kwargs)

                    self.set_media(media_path=default_media, size=0.9)
                    self.set_background_color(color=[255, 255, 255, 255], update=True)

            except Exception:
                self.clear_labels("error")
                self.set_top_label("\nRequest\nFailed", **kwargs)
                self.set_media(media_path=default_media, size=0.9)
                self.set_background_color(color=[255, 255, 255, 255], update=True)
        except Exception:
            self.clear_labels("error")
            self.set_top_label("\nInternal\nError", **kwargs)
            self.set_media(media_path=default_media, size=0.9)
            self.set_background_color(color=[255, 255, 255, 255], update=True)

    def fetch_and_set_commit_status_icons(self, owner, repo, shas):
        import requests
        states = []
        for sha in shas:
            url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/status"
            headers = {
                "Authorization": f"token {self.get_settings().get('github_token', '')}",
                "Accept": "application/vnd.github.v3+json"
            }
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    state = data.get("state", "")
                    states.append(state)
            except Exception:
                continue

        # Set icon based on state priority
        if "failure" in states:
            # Set icon to red
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#A00000.png"), size=0.9)
        elif "pending" in states:
            # Set icon to yellow
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#B7B700.png"), size=0.9)
        elif "success" in states:
            # Set icon to green
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#236B23.png"), size=0.9)

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
