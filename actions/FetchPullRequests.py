# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.PluginManager.PluginBase import PluginBase  # noqa: F401
from src.backend.PluginManager.ActionHolder import ActionHolder  # noqa: F401

# Import python modules
import os
import threading
from loguru import logger as log
import requests

# gi.require_version must be called before any gi.repository imports
import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402
from GtkHelper.GenerativeUI.ComboRow import ComboRow  # noqa: E402


class PullRequestsActions(ActionBase):
    """
    Example Action for PluginTemplate: PullRequests
    This action can be extended to fetch and display pull requests from a repository.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._refresh_timer_id = None
        self._token_change_timeout_id = None
        self._repo_url_change_timeout_id = None
        self._last_settings = None
        self._fetch_lock = threading.Lock()

    def on_ready(self) -> None:
        settings = self.get_settings()
        github_token = self.plugin_base.get_settings().get("github_token", "")
        repo_url = settings.get("repo_url", "")
        owner, repo = self.parse_owner_repo(repo_url)
        if github_token and owner and repo:
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#595959.png"), size=0.9)
            self.fetch_and_display_pull_request_count()
        else:
            self.clear_labels("error")
            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "info.png"), size=0.9)
            self.set_top_label("\nConfigure\nGithub\nPlugin", color=[255, 100, 100], outline_width=1, font_size=17)

        self._last_settings = {**self.plugin_base.get_settings(), **self.get_settings()}
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

    def get_config_rows(self):
        settings = self.get_settings()
        github_token = self.plugin_base.get_settings().get("github_token", "")
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
        refresh_options = ["0 (disabled)", "30 minutes", "60 minutes", "2 hours", "8 hours"]
        valid_options = set(refresh_options)
        default_rate = refresh_rate if refresh_rate in valid_options else "0 (disabled)"
        refresh_rate_row = ComboRow(
            action_core=self,
            var_name="refresh_rate",
            default_value=default_rate,
            items=refresh_options,
            title="Refresh Rate",
            on_change=self.on_refresh_rate_changed,
            auto_add=False
        )

        return [token_entry, repo_entry, refresh_rate_row.widget]

    def on_token_changed(self, entry, *args):
        try:
            from gi.repository import GLib
        except ImportError:
            self.fetch_and_display_pull_request_count()
            return

        if self._token_change_timeout_id is not None:
            GLib.source_remove(self._token_change_timeout_id)
            self._token_change_timeout_id = None

        def do_update():
            plugin_settings = self.plugin_base.get_settings()
            plugin_settings["github_token"] = entry.get_text().strip()
            self.plugin_base.set_settings(plugin_settings)
            self._last_settings = {**plugin_settings, **self.get_settings()}
            self.fetch_and_display_pull_request_count()
            self._token_change_timeout_id = None
            return False  # Only run once

        self._token_change_timeout_id = GLib.timeout_add(500, do_update)

    def on_repo_url_changed(self, entry, *args):
        try:
            from gi.repository import GLib
        except ImportError:
            self.fetch_and_display_pull_request_count()
            return

        if self._repo_url_change_timeout_id is not None:
            GLib.source_remove(self._repo_url_change_timeout_id)
            self._repo_url_change_timeout_id = None

        def do_update():
            settings = self.get_settings()
            settings["repo_url"] = entry.get_text().strip()
            self.set_settings(settings)
            self._last_settings = {**self.plugin_base.get_settings(), **self.get_settings()}
            self.fetch_and_display_pull_request_count()
            self._repo_url_change_timeout_id = None
            return False  # Only run once

        self._repo_url_change_timeout_id = GLib.timeout_add(500, do_update)

    def parse_owner_repo(self, repo_url):
        import re
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/?", repo_url)
        if match:
            owner = match.group(1)
            repo = match.group(2).removesuffix(".git")
            return owner, repo
        return "", ""

    def on_tick(self):
        current_settings = {
            **self.plugin_base.get_settings(),
            **self.get_settings(),
        }
        if current_settings != self._last_settings:
            self._last_settings = current_settings
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

    def clear_labels(self, status):
        self.set_top_label(None)
        self.set_center_label(None)
        self.set_bottom_label(None)
        if status == "success":
            self.set_background_color(color=[0, 0, 0, 0], update=True)
        elif status == "error":
            self.set_background_color(color=[255, 255, 255, 255], update=True)

    def fetch_and_display_pull_request_count(self):
        self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#595959.png"), size=0.9)
        self.set_center_label("Loading...", color=[232, 232, 232], outline_width=1, font_size=14, font_family="cantarell")
        self.set_bottom_label(None)
        t = threading.Thread(target=self._fetch_worker, daemon=True)
        t.start()

    def _fetch_worker(self):
        if not self._fetch_lock.acquire(blocking=False):
            return
        try:
            self._do_fetch_and_display()
        finally:
            self._fetch_lock.release()

    def _do_fetch_and_display(self):
        red = [255, 100, 100]
        kwargs = {"color": red, "outline_width": 1, "font_size": 17, "font_family": "cantarell"}
        default_media = os.path.join(self.plugin_base.PATH, "assets", "info.png")

        try:
            github_token = self.plugin_base.get_settings().get("github_token", "")
            settings = self.get_settings()
            repo_url = settings.get("repo_url", "")
            owner, repo = self.parse_owner_repo(repo_url)
            log.info(f"Fetching pull requests for {owner}/{repo} (token: {github_token[:13]}...)")

            if not owner or not repo or not github_token:
                self.clear_labels("error")
                self.set_top_label("\nConfigure\nGithub\nPlugin", **kwargs)
                self.set_media(media_path=default_media, size=0.9)
                return

            url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github+json"
            }

            try:
                # First 25 most recently updated PRs — used for CI status checks
                first_response = requests.get(url, headers=headers, params={"per_page": 25, "state": "open"}, timeout=10)
                status = first_response.status_code

                if status == 200:
                    first_page = first_response.json()

                    # Count all pages for the total
                    pr_count = len(first_page)
                    next_url = None
                    link = first_response.headers.get("Link", "")
                    for part in link.split(","):
                        if 'rel="next"' in part:
                            next_url = part.split(";")[0].strip().strip("<>")
                            break
                    while next_url:
                        response = requests.get(next_url, headers=headers, timeout=10)
                        if response.status_code != 200:
                            break
                        pr_count += len(response.json())
                        next_url = None
                        link = response.headers.get("Link", "")
                        for part in link.split(","):
                            if 'rel="next"' in part:
                                next_url = part.split(";")[0].strip().strip("<>")
                                break

                    self.clear_labels("success")
                    self.set_center_label(
                        f"{pr_count}", color=[200, 200, 200], outline_width=3, font_size=32, font_family="cantarell"
                    )
                    self.set_bottom_label(
                        "PRs", color=[255, 255, 255], outline_width=2, font_size=15, font_family="cantarell"
                    )
                    self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#595959.png"), size=0.9)
                    if pr_count > 0:
                        shas = [
                            pr["head"]["sha"]
                            for pr in first_page
                            if isinstance(pr.get("head"), dict) and "sha" in pr["head"]
                        ]
                        self.fetch_and_set_commit_status_icons(owner, repo, shas, github_token, pr_count)
                else:
                    self.clear_labels("error")
                    if status == 404:
                        self.set_top_label("\nInvalid\nRepo URL", **kwargs)
                    elif status == 401:
                        self.set_top_label("\nInvalid\nToken", **kwargs)
                    else:
                        self.set_top_label("\nConfigure\nGithub\nPlugin", **kwargs)
                    self.set_media(media_path=default_media, size=0.9)

            except Exception:
                self.clear_labels("error")
                self.set_top_label("\nRequest\nFailed", **kwargs)
                self.set_media(media_path=default_media, size=0.9)
        except Exception:
            self.clear_labels("error")
            self.set_top_label("\nInternal\nError", **kwargs)
            self.set_media(media_path=default_media, size=0.9)

    def fetch_and_set_commit_status_icons(self, owner, repo, shas, github_token, pr_count):
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github+json"
        }

        states = []

        for sha in shas:
            url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs"
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    conclusions = [
                        run.get("conclusion")
                        for run in data.get("check_runs", [])
                        if run.get("status") == "completed" and run.get("conclusion")
                    ]
                    in_progress = any(
                        run.get("status") in ("in_progress", "queued")
                        for run in data.get("check_runs", [])
                    )

                    log.info(f"SHA: {sha}, Check run conclusions: {conclusions}")

                    # Add all conclusions and a sentinel for in-progress runs
                    states.extend(conclusions)
                    if in_progress:
                        states.append("in_progress")
                else:
                    log.warning(f"Failed to fetch check-runs for SHA {sha}: {response.status_code}")
            except Exception as e:
                log.error(f"Exception while fetching check-runs for {sha}: {e}")
                continue

        # Decide icon and count label color based on priority: failure > cancelled/in-progress > success
        if "failure" in states:
            icon_color = "#A00000"
            count_color = [200, 60, 60]
        elif "cancelled" in states or "in_progress" in states:
            icon_color = "#B7B700"
            count_color = [210, 185, 0]
        elif "success" in states:
            icon_color = "#236B23"
            count_color = [80, 200, 80]
        else:
            icon_color = "#595959"
            count_color = [200, 200, 200]

        icon_path = os.path.join(self.plugin_base.PATH, "assets", f"{icon_color}.png")
        self.set_media(media_path=icon_path, size=0.9)
        self.set_center_label(
            f"{pr_count}", color=count_color, outline_width=3, font_size=32, font_family="cantarell"
        )

    # Legacy way of checking
    # def fetch_and_set_commit_status_icons(self, owner, repo, shas):
    #     import requests
    #     states = []
    #     for sha in shas:
    #         url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/status"
    #         headers = {
    #             "Authorization": f"token {self.get_settings().get('github_token', '')}",
    #             "Accept": "application/vnd.github+json"
    #         }
    #         try:
    #             response = requests.get(url, headers=headers, timeout=10)
    #             if response.status_code == 200:
    #                 data = response.json()
    #                 state = data.get("state", "")
    #                 states.append(state)
    #                 log.info(f"URL: {url}, Sha: {sha}, State: {state}")
    #         except Exception:
    #             continue

    #     # Set icon based on state priority
    #     if "failure" in states:
    #         # Set icon to red
    #         self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#A00000.png"), size=0.9)
    #     elif "pending" in states:
    #         # Set icon to yellow
    #         self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#B7B700.png"), size=0.9)
    #     elif "success" in states:
    #         # Set icon to green
    #         self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#236B23.png"), size=0.9)

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

        # Get refresh_rate from settings and convert label to minutes
        settings = self.get_settings()
        rate_label = settings.get("refresh_rate", "0 (disabled)")
        rate_map = {
            "30 minutes": 30,
            "60 minutes": 60,
            "2 hours": 120,
            "8 hours": 480,
        }
        refresh_rate = rate_map.get(rate_label, 0)

        if refresh_rate <= 0:
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
            for timer_id in (
                self._refresh_timer_id,
                self._token_change_timeout_id,
                self._repo_url_change_timeout_id,
            ):
                if timer_id is not None:
                    GLib.idle_add(GLib.source_remove, timer_id)
        except Exception:
            pass
