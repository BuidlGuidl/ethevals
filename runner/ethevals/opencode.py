"""OpenCode that keeps its model keys out of the agent's shell commands."""
import json
import shlex

from harbor.agents.installed.opencode import OpenCode as HarborOpenCode
from harbor.utils.env import is_sensitive_env_key

PLUGIN = "ethevals-hide-keys.js"


class OpenCode(HarborOpenCode):
    """OpenCode's bash tool passes its own environment to every command, keys included.

    Agents that print their environment leaked OPENROUTER_API_KEY into trial files.
    A `shell.env` plugin blanks each credential for shell commands; OpenCode still reads them for its API calls.
    """

    def __init__(self, *args, opencode_config=None, **kwargs):
        config = {**(opencode_config or {})}
        config["plugin"] = [*config.get("plugin", []), f"./{PLUGIN}"]
        super().__init__(*args, opencode_config=config, **kwargs)

    def _hidden_names(self) -> list[str]:
        names = {*self.model_connection.env, *self.extra_env}
        return sorted(name for name in names if is_sensitive_env_key(name))

    def _build_register_config_command(self) -> str | None:
        hidden = json.dumps(self._hidden_names())
        plugin = ("export const HideKeys = async () => ({\n"
                  "  \"shell.env\": async (_input, output) => {\n"
                  f"    for (const name of {hidden}) output.env[name] = \"\";\n"
                  "  },\n"
                  "});\n")
        # The plugin path in opencode.json is relative to that file.
        write = f"mkdir -p ~/.config/opencode && printf %s {shlex.quote(plugin)} > ~/.config/opencode/{PLUGIN}"
        config = super()._build_register_config_command()
        return f"{config} && {write}" if config else write
