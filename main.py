# Import StreamController modules
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import actions
from .actions.PullRequests import PullRequests

class PluginTemplate(PluginBase):
    def __init__(self):
        super().__init__()

        # Register PullRequests action
        self.pull_requests_holder = ActionHolder(
            plugin_base=self,
            action_base=PullRequests,
            action_id="dev_core447_Template::PullRequests",
            action_name="Pull Requests",
        )
        self.add_action_holder(self.pull_requests_holder)

        # Register plugin
        self.register(
            plugin_name="Template",
            github_repo="https://github.com/StreamController/PluginTemplate",
            plugin_version="1.0.0",
            app_version="1.1.1-alpha"
        )
