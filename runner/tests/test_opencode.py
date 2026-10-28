import shlex

from harbor.agents.factory import AgentFactory
from harbor.models.trial.config import AgentConfig

from ethevals.job_config import load_job
from ethevals.opencode import PLUGIN


def agents(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-openrouter-key")
    monkeypatch.setenv("EXA_API_KEY", "offline-exa-key")
    config = load_job()
    for key, agent in config.agents.items():
        if agent.name != "opencode":
            continue
        harbor = AgentConfig(name=None, import_path=agent.import_path, model_name=config.models[agent.model].name,
                             kwargs={"version": agent.version}, env=agent.env)
        yield key, agent, AgentFactory.create_agent_from_config(harbor, logs_dir=tmp_path / key)


def test_every_opencode_agent_hides_its_keys_from_shell_commands(tmp_path, monkeypatch):
    found = list(agents(tmp_path, monkeypatch))
    assert found
    for key, agent, built in found:
        # Results still record the agent as OpenCode at the configured version.
        assert (built.name(), built.version()) == ("opencode", agent.version), key
        command = built._build_register_config_command()
        assert f'"./{PLUGIN}"' in command, key
        plugin = shlex.split(command.split("printf %s ", 1)[1].split(" > ", 1)[0])[0]
        assert '"shell.env"' in plugin
        assert '"OPENROUTER_API_KEY"' in plugin and '"EXA_API_KEY"' in plugin
        # The plugin names variables; it never carries their values.
        assert "offline-" not in command


def test_jobs_pass_only_the_import_path_so_harbor_loads_the_subclass():
    config = load_job()
    agent = config.agents["opencode-glm-5.3"]
    harbor = AgentConfig(name=None if agent.import_path else agent.name, import_path=agent.import_path)
    assert AgentFactory.get_agent_class_from_config(harbor).__module__ == "ethevals.opencode"
