# Import StreamController modules
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.DeckManagement.InputIdentifier import Input

# Import actions
from .actions.FetchPullRequests import PullRequestsActions
from .actions.Contributions import ContributionsActions

class PullRequestsPlugin(PluginBase):
    def __init__(self):
        super().__init__()

        key_only = {
            Input.Key: ActionInputSupport.SUPPORTED,
            Input.Dial: ActionInputSupport.UNSUPPORTED,
            Input.Touchscreen: ActionInputSupport.UNSUPPORTED,
        }

        # Register PullRequests action
        self.pull_requests_holder = ActionHolder(
            plugin_base=self,
            action_base=PullRequestsActions,
            action_id_suffix="PullRequestsActions",
            action_name="Fetch PRs",
            action_support=key_only,
        )
        self.add_action_holder(self.pull_requests_holder)

        # Register Contributions action
        self.contributions_holder = ActionHolder(
            plugin_base=self,
            action_base=ContributionsActions,
            action_id_suffix="ContributionsActions",
            action_name="Contributions",
            action_support=key_only,
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
