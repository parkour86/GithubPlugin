# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import python modules
import os
from loguru import logger as log
import requests
from datetime import datetime, timedelta
from PIL import Image, ImageDraw
from dateutil.relativedelta import relativedelta

# Import gtk modules - used for the config rows (optional, for future UI)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

# Import ComboRow for dropdowns
from GtkHelper.GenerativeUI.ComboRow import ComboRow

import time

class ContributionsActions(ActionBase):
    """
    Action for displaying GitHub contributions by quarter.
    Fetches contribution data using the GitHub GraphQL API and displays summary stats.
    """

    def pad_weeks(self, weeks, start_date, end_date):
        """
        Ensure all weeks between start_date and end_date are present in the weeks list.
        If a week is missing, add it with all contributionCounts set to 0.
        """
        # Convert string dates to datetime
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        # Build a set of all week start dates in your data
        week_starts = set(datetime.strptime(week['contributionDays'][0]['date'], "%Y-%m-%d") for week in weeks)
        # Generate all week start dates in the range
        all_week_starts = []
        current = start
        while current <= end:
            all_week_starts.append(current)
            current += timedelta(days=7)
        # For each missing week, add a week with all 0s
        for week_start in all_week_starts:
            if week_start not in week_starts:
                week = {
                    "contributionDays": [
                        {"contributionCount": 0, "date": (week_start + timedelta(days=i)).strftime("%Y-%m-%d")}
                        for i in range(7)
                        if (week_start + timedelta(days=i)) <= end
                    ]
                }
                weeks.append(week)
        # Sort weeks by their first day
        weeks.sort(key=lambda w: w['contributionDays'][0]['date'])
        return weeks

    # ---- CLASS-LEVEL CACHE ----
    # Keyed by (github_user, github_token, last_date_str)
    _contributions_cache = {}
    _cache_timestamp = None
    _cache_params = None
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
        log.info(f"[MY DEBUG] *{selected_month}*")
        if github_token and github_user:
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
        selected_month = settings.get("selected_month", "")
        self.display_month_row = ComboRow(
            action_core=self,
            var_name="display_contribution_month",
            default_value=selected_month,  # Use the value from settings
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

    def save_contributions_image(self, cell_map, quarter_idx, plugin_path, period_start, period_end):
        """
        Draws a contribution image for the given period.
        Always shows all weeks (Sunday to Saturday) covering the period.
        Out-of-period days are colored white.
        """
        cell_size = 12
        padding = 0
        # Calculate the first Sunday on/before period_start and last Saturday on/after period_end
        first_sunday = period_start - timedelta(days=period_start.weekday() + 1) if period_start.weekday() != 6 else period_start
        last_saturday = period_end + timedelta(days=(5 - period_end.weekday()) % 7)
        # Build all week start dates
        weeks = []
        current = first_sunday
        while current <= last_saturday:
            weeks.append(current)
            current += timedelta(days=7)
        num_cols = len(weeks)
        height = 7 * cell_size + (7 - 1) * padding

        img = Image.new("RGB", (num_cols * (cell_size + padding), height), "white")
        draw = ImageDraw.Draw(img)

        # Build a date->count map for fast lookup
        date_to_count = {}
        for key, (date_str, count) in cell_map.items():
            date_to_count[date_str] = count

        for col, week_start in enumerate(weeks):
            for d in range(7):
                day = week_start + timedelta(days=d)
                x = col * (cell_size + padding)
                y = d * (cell_size + padding)
                box = [x, y, x + cell_size - 1, y + cell_size - 1]
                if period_start <= day <= period_end:
                    count = date_to_count.get(day.strftime("%Y-%m-%d"), 0)
                    color = self.get_color(count)
                else:
                    color = "white"
                draw.rectangle(box, fill=color)
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

            # ---- CACHE LOGIC ----
            cache_key = None
            last_date_str = None
            cache_valid = False
            refresh_rate = settings.get("refresh_rate", "0")
            try:
                refresh_rate = int(refresh_rate)
            except Exception:
                refresh_rate = 0

            # We'll determine last_date after API call or from cache
            # But first, check if we have a cache for this user/token/period
            cache_params = ContributionsActions._cache_params
            cache_timestamp = ContributionsActions._cache_timestamp
            now = time.time()

            # If cache_params exist, check if they match
            if cache_params is not None:
                cached_user, cached_token, cached_last_date_str = cache_params
                if cached_user == github_user and cached_token == github_token:
                    # If refresh_rate is 0, always use cache if available (never refresh from API)
                    # If refresh_rate > 0, use cache only if not expired
                    if ((refresh_rate == 0 and cache_timestamp is not None) or
                        (refresh_rate > 0 and cache_timestamp is not None and (now - cache_timestamp) < refresh_rate * 3600)):
                        cache_key = (github_user, github_token, cached_last_date_str)
                        if cache_key in ContributionsActions._contributions_cache:
                            cache_valid = True
                            last_date_str = cached_last_date_str

            if cache_valid:
                log.info("[CACHE] Using cached contributions data and images.")
                cache = ContributionsActions._contributions_cache[cache_key]
                bimonthly_labels = cache["labels"]
                bimonthly_images = cache["images"]
                bimonthly_counts = cache["counts"]
                # Invalidate cache if selected_month_key is missing from bimonthly_labels
                selected_month_key = self.get_settings().get("selected_month", None)
                label_month_parts = [lbl.split(" (")[0] for lbl in bimonthly_labels]
                if selected_month_key and selected_month_key not in label_month_parts:
                    log.info("[CACHE] selected_month_key missing from bimonthly_labels, invalidating cache.")
                    cache_valid = False
                elif last_date_str is not None:
                    last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
                else:
                    # Cache is invalid or corrupted, force a fresh fetch
                    log.warning("[CACHE] last_date_str is None, forcing fresh fetch.")
                    cache_valid = False

            # After all cache checks, if cache_valid is still False, fetch from API
            if not cache_valid:
                # --- API CALL ---
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
                    log.info(f"[API] Making GitHub contributions API call for button with refresh_rate: {refresh_rate}")
                    response = requests.post(
                        "https://api.github.com/graphql",
                        json={"query": query, "variables": {"login": github_user}},
                        headers=headers,
                        timeout=15
                    )
                    status = response.status_code
                    # import json
                    # with open(os.path.join(self.plugin_base.PATH, "actions/response.json"), "r") as f:
                    #     data = json.load(f)
                    # status = 200

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

                    # Pad the entire weeks_data once to cover the full range
                    all_dates = [day["date"] for week in weeks_data for day in week["contributionDays"]]
                    min_date = min(all_dates)
                    max_date = max(all_dates)
                    weeks_data = self.pad_weeks(weeks_data, min_date, max_date)

                    last_week = weeks_data[-1]
                    last_day = last_week["contributionDays"][-1]["date"]
                    last_date = datetime.strptime(last_day, "%Y-%m-%d")
                    last_date_str = last_day

                    bimonthly_ranges = self.get_bimonthly_ranges(last_date)
                    bimonthly_counts, bimonthly_images, bimonthly_labels = [], [], []
                    plugin_path = self.plugin_base.PATH

                    for idx, (start, end) in enumerate(bimonthly_ranges):
                        count = 0
                        cell_map = {}
                        # Build a date->count map for the period
                        for week in weeks_data:
                            for day in week["contributionDays"]:
                                date_str = day["date"]
                                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                                if start <= date_obj <= end:
                                    c = day["contributionCount"]
                                    cell_map[(date_obj.isocalendar()[1], date_obj.weekday())] = (date_str, c)
                                    count += c
                        bimonthly_counts.append(count)
                        label = f"{start.strftime('%b').upper()}-{end.strftime('%b').upper()} ({count})"
                        bimonthly_labels.append(label)
                        log.info(f"[DEBUG] Built label: {label} with count: {count} for idx: {idx}")
                        # Always generate the image for the full period, even if all zeros
                        img_path = self.save_contributions_image(
                            cell_map, idx, plugin_path,
                            period_start=start, period_end=end
                        )
                        bimonthly_images.append(img_path)

                    # Save to cache
                    cache_key = (github_user, github_token, last_date_str)
                    ContributionsActions._contributions_cache[cache_key] = {
                        "labels": bimonthly_labels,
                        "images": bimonthly_images,
                        "counts": bimonthly_counts,
                    }
                    ContributionsActions._cache_timestamp = now
                    ContributionsActions._cache_params = (github_user, github_token, last_date_str)

                except Exception as e:
                    self.clear_labels("error")
                    self.set_top_label("\nRequest\nFailed", **kwargs)
                    self.set_media(media_path=default_media, size=0.9)
                    self.set_background_color(color=[255, 255, 255, 255], update=True)
                    log.error(f"[DEBUG] API Request Error:{e}", exc_info=True)
                    return

            # Set instance variables from cache or fresh fetch
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

            # Start clean
            self.clear_labels("success")

            def label_month_part(lbl):
                return lbl.split(" (")[0] if lbl else ""

            def find_matching_label(key, labels):
                for lbl in labels:
                    log.info(f"[MY DEBUG] lbl: *{lbl}*, label_month_part: *{label_month_part(lbl)}*, selected_month_key: *{selected_month_key}*")
                    if label_month_part(lbl) == key:
                        return lbl
                return None

            # Pull the selected month from the settings
            selected_month_key = self.get_settings().get("selected_month", None)
            log.info(f"[MY DEBUG] selected_month_key: {selected_month_key}")

            selected_label = None
            # Jump into this loop if the button was just created
            if hasattr(self, "display_month_row") and self.display_month_row is not None:
                # Populate the display_month_row with the bimonthly_labels
                self.display_month_row.populate(
                    bimonthly_labels,
                    selected_item=None,
                    update_settings=False,
                    trigger_callback=False
                )

                if selected_month_key:
                    selected_label = find_matching_label(selected_month_key, bimonthly_labels)

                log.info(f"[App was created] Selected label: {selected_label}")

                if selected_label:
                    self.display_month_row.set_value(selected_label)
                else:
                    selected_label = first_with_data[0] if first_with_data else bimonthly_labels[0]
                    self.display_month_row.set_value(selected_label)
            else:
                # If the selected_month is saved in the settings then loop over the Month Period dropdown options and set the selected_label
                if selected_month_key:
                    selected_label = find_matching_label(selected_month_key, bimonthly_labels)

                if not selected_label:
                    log.info("[MY DEBUG] No match found")
                    rollover_found = False
                    # Try to detect rollover: e.g., if JUL-AUG is gone, look for AUG-SEP
                    if selected_month_key:  # Only try rollover if we have a previous selection
                        try:
                            start, end = selected_month_key.split('-')
                            months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
                            end_idx = months.index(end.upper())
                            next_start_idx = end_idx
                            next_end_idx = (end_idx + 1) % 12
                            next_period = f"{months[next_start_idx]}-{months[next_end_idx]}"
                            log.info(f"[MY DEBUG] Next period: {next_period}")
                            for lbl in bimonthly_labels:
                                log.info(f"[MY DEBUG] Checking label: {lbl}")
                                if lbl.startswith(next_period):
                                    selected_label = lbl
                                    settings["selected_month"] = next_period
                                    self.set_settings(settings)
                                    log.info(f"[ROLLOVER] Detected rollover. Updated selected_month to {next_period}")
                                    rollover_found = True
                                    break
                        except Exception as e:
                            log.warning(f"[ROLLOVER] Failed to parse or find rollover period: {e}")
                    if not rollover_found or not selected_label:
                        selected_label = first_with_data[0] if first_with_data else bimonthly_labels[0]
                        settings["selected_month"] = selected_label.split(" (")[0]
                        self.set_settings(settings)

            log.info(f"[DEBUG] Final selected_label: {selected_label}")

            # Ensure img_path and count match the actual selected label
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

        except Exception as e:
            self.clear_labels("error")
            self.set_top_label("\nInternal\nError", **kwargs)
            self.set_media(media_path=default_media, size=0.9)
            self.set_background_color(color=[255, 255, 255, 255], update=True)
            log.error(f"[DEBUG] API Internal Error:{e}", exc_info=True)

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
