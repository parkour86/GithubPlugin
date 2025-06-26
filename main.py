# Import StreamController modules
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import actions
from .actions.FetchPullRequests import PullRequestsActions
from .actions.Contributions import ContributionsActions

class PullRequestsPlugin(PluginBase):
    def __init__(self):
        super().__init__()

        # Register PullRequests action
        self.pull_requests_holder = ActionHolder(
            plugin_base=self,
            action_base=PullRequestsActions,
            action_id_suffix="PullRequestsActions",
            action_name="Fetch PRs",
        )
        self.add_action_holder(self.pull_requests_holder)

        # Register Contributions action
        self.contributions_holder = ActionHolder(
            plugin_base=self,
            action_base=ContributionsActions,
            action_id_suffix="ContributionsActions",
            action_name="Contributions",
        )
        self.add_action_holder(self.contributions_holder)

        # Register plugin
        lm = self.locale_manager
        self.register(
            plugin_name=lm.get("plugin.name"),
            github_repo="https://github.com/parkour86/GithubPlugin",
            plugin_version="1.0.0",
            app_version="1.1.1-alpha"
        )
