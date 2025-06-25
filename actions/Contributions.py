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
    """
    Action for displaying GitHub contributions by quarter.
    Fetches contribution data using the GitHub GraphQL API and displays summary stats.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        # Placeholder for logic to clear or update UI

    def get_config_rows(self):
        settings = self.get_settings()
        github_token = settings.get("github_token", "")
        github_user = settings.get("github_user", "")
        refresh_rate = settings.get("refresh_rate", "0")

        # Token entry
        token_entry = Adw.EntryRow(title="GitHub Access Token")
        token_entry.set_text(github_token)
        token_entry.connect("notify::text", self.on_token_changed)

        # Username entry
        user_entry = Adw.EntryRow(title="GitHub Username")
        user_entry.set_text(github_user)
        user_entry.connect("notify::text", self.on_user_changed)

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

        # ComboRow for Display Contribution Month
        # Use the quarter month labels as options (e.g., 'Jan-Mar', 'Apr-Jun', etc.)
        quarter_ranges = self.get_quarter_ranges(datetime.now())
        month_labels = [f"{start.strftime('%b')}-{end.strftime('%b')}" for start, end in quarter_ranges]
        display_month_row = ComboRow(
            action_core=self,
            var_name="display_contribution_month",
            default_value="",  # No default selected
            items=month_labels,
            title="Display Contribution Month",
            on_change=self.on_display_month_changed,
            auto_add=False
        )

        # Toggle for Show/Hide Contribution Count (top label)
        show_top_label = settings.get("show_top_label", True)
        show_top_label_row = Adw.SwitchRow(title="Show/Hide Contribution Count")
        show_top_label_row.set_active(show_top_label)
        show_top_label_row.connect("notify::active", self.on_show_top_label_changed)

        # Toggle for Show/Hide Bottom Label
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
        settings = self.get_settings()
        settings["github_token"] = entry.get_text()
        self.set_settings(settings)
        self.fetch_and_display_contributions()

    def on_user_changed(self, entry, *args):
        settings = self.get_settings()
        settings["github_user"] = entry.get_text()
        self.set_settings(settings)
        self.fetch_and_display_contributions()

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
            self.set_background_color(color=[255, 255, 255, 255], update=True)

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
        # value is the selected label, e.g., "Jul-Sep"
        settings = self.get_settings()
        selected_label = value.get_value() if hasattr(value, "get_value") else value
        # Try to find the corresponding image for the selected label
        # Use cached quarter_labels and quarter_images if available
        if hasattr(self, "_quarter_labels") and hasattr(self, "_quarter_images"):
            if selected_label in self._quarter_labels:
                idx = self._quarter_labels.index(selected_label)
                img_path = self._quarter_images[idx]
                if img_path:
                    self.set_media(media_path=img_path, size=0.49)

    @staticmethod
    def get_quarter_ranges(last_date):
        year = last_date.year
        month = last_date.month
        prev_year = year - 1
        return [
            (datetime(prev_year, 7, 1), datetime(prev_year, 9, 30)),  # Q3 prev year
            (datetime(prev_year, 10, 1), datetime(prev_year, 12, 31)), # Q4 prev year
            (datetime(year, 1, 1), datetime(year, 3, 31)),            # Q1 current year
            (datetime(year, 4, 1), datetime(year, 6, 30))             # Q2 current year
        ]

    def get_color(self, count):
        # GitHub-like color scale
        if count == 0:
            return "#ebedf0"
        elif count < 8:
            return "#c6e48b"
        elif count < 15:
            return "#7bc96f"
        elif count < 22:
            return "#239a3b"
        else:
            return "#196127"

    def save_contributions_image(self, cell_map, sorted_weeks, quarter_idx, plugin_path):
        # Image config
        cell_size = 12
        padding = 2
        height = 7 * cell_size + (7 - 1) * padding
        num_weeks = len(sorted_weeks)
        num_cols = max(14, num_weeks)
        img = Image.new("RGB", (num_cols * (cell_size + padding), height), "white")
        draw = ImageDraw.Draw(img)
        for local_w in range(num_cols):
            for d in range(7):
                if local_w < num_weeks:
                    real_w = sorted_weeks[local_w]
                    key = (real_w, d)
                    if key in cell_map:
                        _, count = cell_map[key]
                        color = self.get_color(count)
                    else:
                        color = "white"
                else:
                    color = "white"
                x = local_w * (cell_size + padding)
                y = d * (cell_size + padding)
                draw.rectangle([x, y, x + cell_size, y + cell_size], fill=color)
        img_path = os.path.join(plugin_path, f"contributions_img{quarter_idx+1}.png")
        img.save(img_path)
        return img_path

    def fetch_and_display_contributions(self):
        # Common red label parameters
        red = [255, 100, 100]
        kwargs = {"color": red, "outline_width": 1, "font_size": 17, "font_family": "cantarell"}
        default_media = os.path.join(self.plugin_base.PATH, "assets", "info.png")

        try:
            settings = self.get_settings()
            github_token = settings.get("github_token", "")
            github_user = settings.get("github_user", "")
            log.info(f"[DEBUG] Fetching contributions for {github_user}")

            if not github_token or not github_user:
                self.clear_labels("error")
                self.set_background_color(color=[255, 255, 255, 255], update=True)
                self.set_top_label("\nConfigure\nContributions\nPlugin", **kwargs)
                self.set_media(media_path=default_media, size=0.9)
                return

            query = """
            query($login: String!) {
            user(login: $login) {
                contributionsCollection {
                contributionCalendar {
                    weeks {
                    contributionDays {
                        contributionCount
                        date
                    }
                    }
                }
                }
            }
            }
            """

            headers = {
                "Authorization": f"Bearer {github_token}"
            }

            try:
                response = requests.post(
                    "https://api.github.com/graphql",
                    json={"query": query, "variables": {"login": github_user}},
                    headers=headers,
                    timeout=15
                )
                status = response.status_code

                if status != 200:
                    self.clear_labels("error")
                    label = "\nInvalid\nToken" if status == 401 else "\nAPI\nError"
                    self.set_top_label(label, **kwargs)
                    self.set_media(media_path=default_media, size=0.9)
                    self.set_background_color(color=[255, 255, 255, 255], update=True)
                    return

                data = response.json()
                if "data" not in data or data["data"]["user"] is None:
                    self.clear_labels("error")
                    self.set_top_label("\nUser\nNot Found", **kwargs)
                    self.set_media(media_path=default_media, size=0.9)
                    self.set_background_color(color=[255, 255, 255, 255], update=True)
                    return

                weeks_data = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
                if not weeks_data:
                    self.clear_labels("error")
                    self.set_top_label("\nNo\nData", **kwargs)
                    self.set_media(media_path=default_media, size=0.9)
                    self.set_background_color(color=[255, 255, 255, 255], update=True)
                    return

                # Find the last date in the dataset (last day of last week)
                last_week = weeks_data[-1]
                last_day = last_week["contributionDays"][-1]["date"]
                last_date = datetime.strptime(last_day, "%Y-%m-%d")

                # Use staticmethod for quarter ranges
                quarter_ranges = self.get_quarter_ranges(last_date)
                quarter_counts = []
                quarter_images = []
                plugin_path = self.plugin_base.PATH

                quarter_labels = []
                for idx, (start, end) in enumerate(quarter_ranges):
                    count = 0
                    cell_map = {}
                    week_indices = set()
                    for week_idx, week in enumerate(weeks_data):
                        for day_idx, day in enumerate(week["contributionDays"]):
                            date_str = day["date"]
                            c = day["contributionCount"]
                            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                            if start <= date_obj <= end:
                                cell_map[(week_idx, day_idx)] = (date_str, c)
                                week_indices.add(week_idx)
                                count += c
                    quarter_counts.append(count)
                    label = f"{start.strftime('%b')}-{end.strftime('%b')}"
                    quarter_labels.append(label)
                    if week_indices:
                        sorted_weeks = sorted(week_indices)
                        img_path = self.save_contributions_image(cell_map, sorted_weeks, idx, plugin_path)
                        quarter_images.append(img_path)
                    else:
                        quarter_images.append(None)

                # Cache for ComboRow on_change
                self._quarter_labels = quarter_labels
                self._quarter_images = quarter_images

                # Display the most recent quarter with data and image
                for i in reversed(range(4)):
                    if quarter_counts[i] > 0:
                        qnum = i + 1
                        start, end = quarter_ranges[i]
                        label = quarter_labels[i]
                        self.clear_labels("success")
                        # Show/hide top label (contribution count)
                        show_top_label = self.get_settings().get("show_top_label", True)
                        if show_top_label:
                            self.set_top_label(f"{quarter_counts[i]}", color=[100, 255, 100], outline_width=4, font_size=18, font_family="cantarell")
                        else:
                            self.set_top_label(None)
                        # Show/hide bottom label
                        show_bottom_label = self.get_settings().get("show_bottom_label", True)
                        if show_bottom_label:
                            self.set_bottom_label(label, color=[100, 200, 255], outline_width=2, font_size=18, font_family="cantarell")
                        else:
                            self.set_bottom_label(None)
                        # Show the generated image for this quarter if available
                        if quarter_images[i]:
                            self.set_media(media_path=quarter_images[i], size=0.49)
                        else:
                            self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "#595959.png"), size=0.9)
                        break
                else:
                    self.clear_labels("error")
                    self.set_top_label("\nNo\nContributions", **kwargs)
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
                self.fetch_and_display_contributions()
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
