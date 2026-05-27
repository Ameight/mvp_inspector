"""Тесты для sdk/base_plugin.py — PluginInterface."""
import pytest
from sdk.base_plugin import PluginInterface, app_log, _logs


# ── Вспомогательные классы ────────────────────────────────────────────────────

class MinimalPlugin(PluginInterface):
    """Минимальная реализация — только обязательный run()."""
    def run(self, inputs: dict) -> str:
        return "ok"


class FullPlugin(PluginInterface):
    """Плагин с переопределёнными методами."""
    def run(self, inputs: dict) -> str:
        return f"result: {inputs.get('query', '')}"

    def get_display_name(self) -> str:
        return "Full Plugin"

    def get_description(self) -> str:
        return "Описание плагина"

    def get_category(self) -> str:
        return "DevOps"

    def get_required_env(self) -> dict:
        return {
            "MY_TOKEN": {"label": "Token", "secret": True},
        }

    def get_config_schema(self) -> dict:
        return {
            "query": {"label": "Запрос", "type": "string", "default": ""},
        }


class DisabledPlugin(PluginInterface):
    def run(self, inputs: dict) -> str:
        return ""

    def is_enabled(self) -> bool:
        return False


# ── get_config_key ────────────────────────────────────────────────────────────

class TestGetConfigKey:
    def test_strips_plugin_suffix(self):
        class JiraCheckerPlugin(PluginInterface):
            def run(self, inputs): return ""

        assert JiraCheckerPlugin().get_config_key() == "jira_checker"

    def test_no_plugin_suffix(self):
        class MyTool(PluginInterface):
            def run(self, inputs): return ""

        assert MyTool().get_config_key() == "my_tool"

    def test_single_word(self):
        class DeployPlugin(PluginInterface):
            def run(self, inputs): return ""

        assert DeployPlugin().get_config_key() == "deploy"

    def test_camel_case_without_suffix(self):
        class GitLabRunner(PluginInterface):
            def run(self, inputs): return ""

        assert GitLabRunner().get_config_key() == "git_lab_runner"

    def test_all_lowercase(self):
        class simpleplugin(PluginInterface):
            def run(self, inputs): return ""

        assert simpleplugin().get_config_key() == "simpleplugin"


# ── Defaults ──────────────────────────────────────────────────────────────────

class TestDefaults:
    def test_category_default(self):
        assert MinimalPlugin().get_category() == "General"

    def test_is_enabled_default(self):
        assert MinimalPlugin().is_enabled() is True

    def test_disabled_plugin(self):
        assert DisabledPlugin().is_enabled() is False

    def test_display_name_default(self):
        assert MinimalPlugin().get_display_name() == "MinimalPlugin"

    def test_description_default(self):
        assert MinimalPlugin().get_description() == ""

    def test_required_env_default(self):
        assert MinimalPlugin().get_required_env() == {}

    def test_config_schema_default(self):
        assert MinimalPlugin().get_config_schema() == {}


# ── configure ─────────────────────────────────────────────────────────────────

class TestConfigure:
    def test_configure_stores_config(self):
        p = MinimalPlugin()
        p.configure({"url": "https://example.com", "timeout": 30})
        assert p.config["url"] == "https://example.com"
        assert p.config["timeout"] == 30

    def test_configure_empty(self):
        p = MinimalPlugin()
        p.configure({})
        assert p.config == {}

    def test_configure_overrides_previous(self):
        p = MinimalPlugin()
        p.configure({"key": "old"})
        p.configure({"key": "new"})
        assert p.config["key"] == "new"


# ── run ───────────────────────────────────────────────────────────────────────

class TestRun:
    def test_minimal_run(self):
        assert MinimalPlugin().run({}) == "ok"

    def test_full_run_with_input(self):
        p = FullPlugin()
        assert p.run({"query": "test"}) == "result: test"

    def test_full_run_missing_input(self):
        p = FullPlugin()
        assert p.run({}) == "result: "

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            PluginInterface()


# ── log ───────────────────────────────────────────────────────────────────────

class TestLog:
    def test_log_appends_to_logs(self):
        initial_count = len(_logs)
        p = FullPlugin()
        p.log("test message", level="debug")
        assert len(_logs) == initial_count + 1
        last = _logs[-1]
        assert last["message"] == "test message"
        assert last["level"] == "debug"
        assert last["source"] == "Full Plugin"

    def test_log_default_level_is_info(self):
        p = MinimalPlugin()
        p.log("info message")
        assert _logs[-1]["level"] == "info"


# ── FullPlugin итоговая проверка ─────────────────────────────────────────────

class TestFullPlugin:
    def test_all_metadata(self):
        p = FullPlugin()
        assert p.get_display_name() == "Full Plugin"
        assert p.get_description() == "Описание плагина"
        assert p.get_category() == "DevOps"
        assert "MY_TOKEN" in p.get_required_env()
        assert p.get_required_env()["MY_TOKEN"]["secret"] is True
        assert "query" in p.get_config_schema()
