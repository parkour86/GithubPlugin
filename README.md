# GithubPlugin

## Index

- [Pre-Requirements](#pre-requirements)
- [Overview](#overview)
- [Example Screenshot](#example-screenshot)
- [FetchPullRequests.py](#fetchpullrequestspy)
  - [Features](#features)
  - [Configuration](#configuration)
  - [How It Works](#how-it-works)
- [Contributions.py](#contributionspy)
  - [Features](#features-1)
  - [Configuration](#configuration-1)
  - [How It Works](#how-it-works-1)
- [Usage](#usage)

---

## Pre-Requirements

- Before using this plugin, you must generate a GitHub [personal access token](https://github.com/settings/tokens).
- You can select the scopes you'd like to add—this token will be used for the **GitHub Access Token** field in the plugin settings.

---

## Overview

This plugin provides two main actions for integrating GitHub data into your [StreamController](https://streamcontroller.core447.com/) setup:

- **FetchPullRequests.py**: Displays pull request counts and statuses for a configured repository.
- **Contributions.py**: Visualizes user contribution activity over time.

---

## Example Screenshot

![Example](assets/Example.png)

---

## FetchPullRequests.py

### Features

- Fetches and displays the total number of open pull requests for a specified GitHub repository (supports repos with 100+ PRs via pagination).
- Shows a colored status icon based on CI check-run results from the 25 most recently updated PRs.
- The PR count updates its color to match the CI status once check-runs are resolved.
- Shows a "Loading..." indicator while data is being fetched in the background.
- Provides quick access to the repository's pull requests page by pressing the key.
- Periodically refreshes data based on a configurable interval.

### Configuration

- **GitHub Access Token**: Required for authenticated API requests. Generate a personal access token with appropriate scopes.
- **Repository URL**: The full URL of the GitHub repository (e.g., `https://github.com/owner/repo`).
- **Refresh Rate**: How often (in minutes) to update the pull request count and status. Set to `0` to disable auto-refresh.

### How It Works

1. **Initialization**: On startup, the action checks for a valid token and repository URL. If missing, it prompts for configuration.
2. **Fetching PRs**: Uses the GitHub API to paginate through all open pull requests for an accurate total count, then displays it as a large centered number.
3. **Status Icon**: Fetches check-run results for the 25 most recently updated PRs and sets the background icon and count color accordingly:
   - Red: One or more check-runs failed
   - Yellow: Runs are cancelled or still in progress
   - Green: All check-runs passed
   - Gray: No check-run data found
4. **UI Integration**: Provides configuration rows for token, repo URL, and refresh rate. Pressing the key opens the PRs page in a browser.
5. **Auto-Refresh**: Uses a timer to periodically update the display based on the configured refresh rate.

---

## Contributions.py

### Features

- Visualizes a user's GitHub contributions (commits, PRs, etc.) over time.
- Supports bimonthly display ranges.
- Customizable display options (show/hide top/bottom labels and select user).
- Periodic refresh to keep contribution data up-to-date.

### Configuration

- **GitHub Access Token**: Required for authenticated API requests.
- **GitHub Username**: The user whose contributions you want to display.
- **Refresh Rate**: How often (in minutes) to update the contributions data.
- **Display Options**: Toggle visibility of top/bottom labels, select display month, and more.

### How It Works

1. **Initialization**: Loads settings and prepares the UI for configuration.
2. **Fetching Contributions**: Uses the GitHub API to retrieve and process the user's contribution data.
3. **Visualization**: Renders a graphical representation of contributions, with color-coding and optional labels.
4. **Customization**: Offers UI controls for adjusting the display, including which month(s) to show and label visibility.
5. **Auto-Refresh**: Periodically updates the contribution graph based on the refresh rate.

---

## Usage

1. **Generate a GitHub personal access token**
   (You can allow only the scopes required for your query.)
2. **Configure the plugin**
   - Enter your token under "GitHub Access Token" in the settings.
   - For PullRequests, specify the repository URL.
   - For Contributions, specify the GitHub username.
3. **Adjust refresh rates and display options as desired.**

---
