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
from dateutil.relativedelta import relativedelta

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
        self._token_change_timeout_id = None
        self._user_change_timeout_id = None
        self._refresh_timer_id = None  # For periodic refresh

    def on_ready(self) -> None:
        settings = self.get_settings()
        github_token = settings.get("github_token", "")
        github_user = settings.get("github_user", "")
        selected_month = settings.get("selected_month", "")
        log.info(f"[MY DEBUG] {selected_month}")
        if github_token and github_user:
            #self.set_media(media_path=os.path.join(self.plugin_base.PATH, "assets", "info.png"), size=0.9)
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

        # ComboRow for refresh rate (hours)
        refresh_options = ["0", "1", "6", "12", "24"]
        refresh_rate_row = ComboRow(
            action_core=self,
            var_name="refresh_rate",
            default_value=str(refresh_rate),
            items=refresh_options,
            title="Refresh Rate (hours)",
            on_change=self.on_refresh_rate_changed,
            auto_add=False
        )

        # ComboRow for Display Contribution Month
        # Only show periods for which images/data exist (populated after fetch)
        month_labels = None
        if hasattr(self, "_quarter_labels") and hasattr(self, "_quarter_images"):
            # Only include periods for which an image exists (not None)
            month_labels = [
                label for label, img in zip(self._quarter_labels, self._quarter_images) if img is not None
            ]
        if not month_labels or len(month_labels) == 0:
            # fallback to all possible periods if not yet populated
            bimonthly_ranges = self.get_bimonthly_ranges(datetime.now())
            month_labels = [f"{start.strftime('%b')}-{end.strftime('%b')}" for start, end in bimonthly_ranges]
        self.display_month_row = ComboRow(
            action_core=self,
            var_name="display_contribution_month",
            default_value="",  # No default selected
            items=month_labels,
            title="Display Contribution Period",
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
            self.display_month_row.widget,
            show_top_label_row,
            show_bottom_label_row,
        ]

    def on_token_changed(self, entry, *args):
        from gi.repository import GLib
        # Cancel any pending timeout
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
            github_user = settings.get("github_user", "")
            if github_user.strip():
                self.fetch_and_display_contributions()
            self._token_change_timeout_id = None
            return False  # Only run once

        # Debounce: schedule after 500ms
        self._token_change_timeout_id = GLib.timeout_add(500, do_update)

    def on_user_changed(self, entry, *args):
        from gi.repository import GLib
        # Cancel any pending timeout
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
            github_token = settings.get("github_token", "")
            if github_token.strip():
                self.fetch_and_display_contributions()
            self._user_change_timeout_id = None
            return False  # Only run once

        # Debounce: schedule after 500ms
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
            self.set_background_color(color=[255, 255, 255, 255], update=True)

    def refresh_ui_from_dropdown(self):
        # Get the current value from the ComboRow and update the UI
        if hasattr(self, "display_month_row") and self.display_month_row is not None:
            value = self.display_month_row.get_value() if hasattr(self.display_month_row, "get_value") else None
            if value:
                self.on_display_month_changed(self.display_month_row, value, None)

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
        # Save only the month part to settings for refresh restoration
        month_part = selected_label.split(" (")[0] if selected_label else ""
        log.info(f"[DEBUG] on_display_month_changed: Saving selected_month = {month_part}")
        settings["selected_month"] = month_part
        self.set_settings(settings)
        log.info(f"[DEBUG] on_display_month_changed: settings after save: {self.get_settings()}")

        if hasattr(self, "_quarter_labels") and hasattr(self, "_quarter_images") and hasattr(self, "_quarter_counts"):
            filtered = [
                (label, img, count) for label, img, count in zip(self._quarter_labels, self._quarter_images, self._quarter_counts) if img is not None
            ]
            filtered_labels = [label for label, img, count in filtered]
            filtered_images = [img for label, img, count in filtered]
            filtered_counts = [count for label, img, count in filtered]

            if selected_label in filtered_labels:
                idx = filtered_labels.index(selected_label)
                img_path = filtered_images[idx]
                count = filtered_counts[idx]
                if img_path:
                    self.set_media(media_path=img_path, size=0.68, valign=-.7)

                # ✅ Update the top label (contribution count) for the selected period
                show_top_label = settings.get("show_top_label", True)
                if show_top_label:
                    self.set_top_label(
                        f"{count}",
                        color=[100, 255, 100],
                        outline_width=4,
                        font_size=18,
                        font_family="cantarell"
                    )
                else:
                    self.set_top_label(None)

                # ✅ Update the bottom label too
                show_bottom_label = settings.get("show_bottom_label", True)
                if show_bottom_label:
                    # Show only the month range (without count) in the bottom label
                    self.set_bottom_label(
                        selected_label.split(" (")[0],
                        color=[100, 255, 100],
                        outline_width=2,
                        font_size=16,
                        font_family="cantarell"
                    )
                else:
                    self.set_bottom_label(None)

    @staticmethod
    def get_bimonthly_ranges(last_date):
        # Go back 6 bimonthly periods (12 months total)
        ranges = []
        current_end = last_date.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)
        for _ in range(6):
            current_start = current_end.replace(day=1) - relativedelta(months=1)
            ranges.insert(0, (current_start, current_end))  # prepend
            current_end = current_start - relativedelta(days=1)
        return ranges

    # def get_color(self, count):
    #     # GitHub-like color scale
    #     if count == 0:
    #         return "#3d444d" # "#ebedf0"
    #     elif count < 8:
    #         return "#c6e48b"
    #     elif count < 15:
    #         return "#7bc96f"
    #     elif count < 22:
    #         return "#239a3b"
    #     else:
    #         return "#196127"
    def get_color(self, count):
        if count == 0:
            return "#3d444d"  # dark gray (inactive)
        elif count < 8:
            return "#2d8659"  # strong, deep green
        elif count < 15:
            return "#4ca96c"  # darker desaturated green
        elif count < 22:
            return "#73c48f"  # medium soft green
        else:
            return "#a3d9a5"  # light muted green

    def save_contributions_image(self, cell_map, sorted_weeks, quarter_idx, plugin_path):
        cell_size = 12
        padding = 0  # ← Set padding to 0 to remove spacing
        height = 7 * cell_size + (7 - 1) * padding
        num_weeks = len(sorted_weeks)
        #num_cols = max(10, num_weeks)
        num_cols = num_weeks

        # Make background fully white
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
                box = [x, y, x + cell_size - 1, y + cell_size - 1]

                # Fill the cell (white or colored)
                draw.rectangle(box, fill=color)

                # Only draw border if it's an active (green) cell
                # if color.lower() not in ["#3d444d", "white"]:
                #     draw.rectangle(box, outline="black", width=1)

                # Draw border if it's an active (green) cell
                #if color.lower() in ["#3d444d"]:
                draw.rectangle(box, outline="#777777", width=1)

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
                log.info("[DEBUG] No github_token or github_user, aborting fetch_and_display_contributions")
                self.clear_labels("error")
                self.set_background_color(color=[255, 255, 255, 255], update=True)
                self.set_top_label("\nConfigure\nGithub\nPlugin", **kwargs)
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

                last_week = weeks_data[-1]
                last_day = last_week["contributionDays"][-1]["date"]
                last_date = datetime.strptime(last_day, "%Y-%m-%d")

                bimonthly_ranges = self.get_bimonthly_ranges(last_date)
                bimonthly_counts, bimonthly_images, bimonthly_labels = [], [], []
                plugin_path = self.plugin_base.PATH

                for idx, (start, end) in enumerate(bimonthly_ranges):
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
                    bimonthly_counts.append(count)
                    label = f"{start.strftime('%b').upper()}-{end.strftime('%b').upper()} ({count})"
                    bimonthly_labels.append(label)
                    log.info(f"[DEBUG] Built label: {label} with count: {count} for idx: {idx}")
                    if week_indices:
                        img_path = self.save_contributions_image(cell_map, sorted(week_indices), idx, plugin_path)
                        bimonthly_images.append(img_path)
                    else:
                        bimonthly_images.append(None)

                self._quarter_labels = bimonthly_labels
                self._quarter_images = bimonthly_images
                self._quarter_counts = bimonthly_counts

                log.info(f"[DEBUG] All bimonthly_labels: {bimonthly_labels}")
                log.info(f"[DEBUG] All bimonthly_counts: {bimonthly_counts}")

                first_with_data = next(
                    ((lbl, img, cnt) for lbl, img, cnt in zip(bimonthly_labels, bimonthly_images, bimonthly_counts) if cnt > 0),
                    (None, None, None)
                )

                if first_with_data[0] is None:
                    log.info("[DEBUG] No data found for any period, aborting.")
                    self.clear_labels("error")
                    self.set_top_label("\nActivity\nLog\nEmpty", **kwargs)
                    self.set_media(media_path=default_media, size=0.9)
                    self.set_background_color(color=[255, 255, 255, 255], update=True)
                    return

                # Begin rendering content
                label, img_path, count = first_with_data
                self.clear_labels("success")

                selected_label = label  # default to first with data
                month_key = None

                if hasattr(self, "display_month_row") and self.display_month_row is not None:
                    month_key = self.get_settings().get("selected_month", None)
                    current_items = getattr(self.display_month_row, "items", None)

                    def label_month_part(lbl):
                        return lbl.split(" (")[0] if lbl else ""

                    log.info(f"[DEBUG] Current month_key from settings: {month_key}")
                    log.info(f"[DEBUG] Current ComboRow items: {current_items}")

                    # Always populate the ComboRow to ensure it's synced
                    self.display_month_row.populate(
                        bimonthly_labels,
                        selected_item=None,  # initially unset
                        update_settings=False,
                        trigger_callback=False
                    )

                    # Try to match stored month key to actual label
                    if month_key:
                        for lbl in bimonthly_labels:
                            if label_month_part(lbl) == month_key:
                                selected_label = lbl
                                break

                    # Set the dropdown visually to the selected label
                    self.display_month_row.set_value(selected_label)

                    # if current_items is None or list(current_items) != list(bimonthly_labels):
                    #     if month_key:
                    #         for lbl in bimonthly_labels:
                    #             if label_month_part(lbl) == month_key:
                    #                 selected_label = lbl
                    #                 break

                    #     log.info(f"[DEBUG] Populating ComboRow with labels: {bimonthly_labels}, selected_label: {selected_label}")
                    #     self.display_month_row.populate(
                    #         bimonthly_labels,
                    #         selected_item=selected_label,
                    #         update_settings=False,
                    #         trigger_callback=False
                    #     )
                    #     # Save only the month key
                    #     self.get_settings()["selected_month"] = label_month_part(selected_label)


                    # else:
                    #     if month_key:
                    #         for lbl in bimonthly_labels:
                    #             if label_month_part(lbl) == month_key:
                    #                 selected_label = lbl
                    #                 break

                log.info(f"[DEBUG] Final selected_label: {selected_label}")

                # Ensure img_path and count match the actual selected label
                if selected_label not in bimonthly_labels:
                    log.info(f"[DEBUG] selected_label '{selected_label}' not in bimonthly_labels, defaulting to first.")
                    selected_label = bimonthly_labels[0]
                idx = bimonthly_labels.index(selected_label)
                img_path = bimonthly_images[idx]
                count = bimonthly_counts[idx]
                log.info(f"[DEBUG] Using idx: {idx}, img_path: {img_path}, count: {count} for selected_label: {selected_label}")

                # Top label (count)
                if self.get_settings().get("show_top_label", True):
                    log.info(f"[DEBUG] Setting top label to count: {count}")
                    self.set_top_label(
                        f"{count}",
                        color=[100, 255, 100],
                        outline_width=4,
                        font_size=18,
                        font_family="cantarell"
                    )
                else:
                    log.info("[DEBUG] Hiding top label")
                    self.set_top_label(None)

                # Bottom label (month range)
                if self.get_settings().get("show_bottom_label", True):
                    log.info(f"[DEBUG] Setting bottom label to: {selected_label.split(' (')[0]}")
                    self.set_bottom_label(
                        selected_label.split(" (")[0],
                        color=[100, 255, 100],
                        outline_width=2,
                        font_size=16,
                        font_family="cantarell"
                    )
                else:
                    log.info("[DEBUG] Hiding bottom label")
                    self.set_bottom_label(None)

                # Set contribution image
                if img_path:
                    log.info(f"[DEBUG] Setting media to img_path: {img_path}")
                    self.set_media(media_path=img_path, size=0.68, valign=-.7)
                else:
                    log.info(f"[DEBUG] Setting media to default_media: {default_media}")
                    self.set_media(media_path=default_media, size=0.9)

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

#



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
        refresh_rate = settings.get("refresh_rate", "0")
        try:
            refresh_rate = int(refresh_rate)
        except Exception:
            refresh_rate = 0

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
            # Refresh rate interval in hours
            self._refresh_timer_id = GLib.timeout_add_seconds(refresh_rate * 3600, _timer_callback)
            # Refresh rate interval in minutes
            #self._refresh_timer_id = GLib.timeout_add_seconds(refresh_rate * 60, _timer_callback)
            #
            #

        except Exception:
            self._refresh_timer_id = None

    def __del__(self):
        try:
            from gi.repository import GLib
            if self._refresh_timer_id is not None:
                GLib.source_remove(self._refresh_timer_id)
        except Exception:
            pass
