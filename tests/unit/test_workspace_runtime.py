"""Tests for runtime workspace / working-directory behavior."""

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from kohakuterrarium.core.config import AgentConfig
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.core.session import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = PROJECT_ROOT
AGENT_DIR = PROJECT_ROOT / "examples" / "agent-apps" / "swe_agent"
LAUNCH_DIR = PROJECT_ROOT / "terrariums" / "swe_team"


class TestAgentExecutorWorkspace:
    """Agent executor should use the runtime cwd, not the agent config dir."""

    def test_init_executor_uses_process_cwd(self, monkeypatch):
        from kohakuterrarium.core.agent_init import AgentInitMixin

        original_cwd = Path.cwd()
        monkeypatch.chdir(WORKSPACE_DIR)

        mixin = object.__new__(AgentInitMixin)
        mixin.config = AgentConfig(name="test", agent_path=AGENT_DIR)
        mixin.registry = Registry()
        mixin._explicit_session = Session("workspace-test")
        mixin.environment = None

        mixin._init_executor()

        assert mixin.executor._working_dir == WORKSPACE_DIR.resolve()
        assert mixin._path_guard.cwd == str(WORKSPACE_DIR.resolve())
        monkeypatch.chdir(original_cwd)


class TestRunCliWorkspace:
    """CLI run path should honor --pwd as the runtime workspace."""

    def test_run_agent_cli_changes_to_pwd_before_agent_creation(self, monkeypatch):
        import kohakuterrarium.__main__ as cli

        original_cwd = Path.cwd()
        monkeypatch.chdir(LAUNCH_DIR)

        seen: dict[str, str] = {}

        class FakeAgent:
            config = SimpleNamespace(name="demo")

            def attach_session_store(self, store):
                return None

            async def run(self):
                seen["cwd_in_run"] = str(Path.cwd())

        def fake_from_path(path: str):
            seen["agent_path"] = path
            seen["cwd_before_create"] = str(Path.cwd())
            return FakeAgent()

        monkeypatch.setattr(cli.Agent, "from_path", staticmethod(fake_from_path))

        exit_code = cli.run_agent_cli(
            str(AGENT_DIR),
            "INFO",
            session=None,
            pwd=str(WORKSPACE_DIR),
        )

        assert exit_code == 0
        assert seen["agent_path"] == str(AGENT_DIR.resolve())
        assert seen["cwd_before_create"] == str(WORKSPACE_DIR.resolve())
        assert seen["cwd_in_run"] == str(WORKSPACE_DIR.resolve())
        monkeypatch.chdir(original_cwd)


class TestDotenvDiscovery:
    """CLI dotenv loading should fall back from workspace to config tree."""

    def test_detect_dotenv_starts_prefers_pwd_but_includes_config(self):
        import kohakuterrarium.__main__ as cli

        args = argparse.Namespace(
            command="terrarium",
            terrarium_path=str(LAUNCH_DIR),
            pwd=str(PROJECT_ROOT / ".." / "Switchyard"),
        )

        starts = cli._detect_dotenv_starts(args)

        assert starts[0] == (PROJECT_ROOT / ".." / "Switchyard").resolve()
        assert LAUNCH_DIR.resolve() in starts

    def test_load_local_dotenv_falls_back_to_config_tree(self, monkeypatch):
        import kohakuterrarium.__main__ as cli

        workspace = (PROJECT_ROOT / ".." / "Switchyard").resolve()
        loaded: list[Path] = []
        real_exists = Path.exists

        def fake_exists(path_obj: Path) -> bool:
            if path_obj.name == ".env":
                return path_obj.parent == PROJECT_ROOT
            return real_exists(path_obj)

        def fake_load_dotenv(dotenv_path, override=False):
            loaded.append(Path(dotenv_path))

        monkeypatch.setattr(Path, "exists", fake_exists, raising=False)
        monkeypatch.setattr(cli, "load_dotenv", fake_load_dotenv)

        found = cli._load_local_dotenv([workspace, LAUNCH_DIR])

        assert found == PROJECT_ROOT / ".env"
        assert loaded == [PROJECT_ROOT / ".env"]

    def test_load_local_dotenv_layers_workspace_then_repo(self, monkeypatch):
        import kohakuterrarium.__main__ as cli

        workspace = (PROJECT_ROOT / ".." / "Switchyard").resolve()
        loaded: list[Path] = []
        real_exists = Path.exists

        def fake_exists(path_obj: Path) -> bool:
            if path_obj.name == ".env":
                return path_obj.parent in {workspace, PROJECT_ROOT}
            return real_exists(path_obj)

        def fake_load_dotenv(dotenv_path, override=False):
            loaded.append(Path(dotenv_path))

        monkeypatch.setattr(Path, "exists", fake_exists, raising=False)
        monkeypatch.setattr(cli, "load_dotenv", fake_load_dotenv)

        found = cli._load_local_dotenv([workspace, LAUNCH_DIR])

        assert found == workspace / ".env"
        assert loaded == [workspace / ".env", PROJECT_ROOT / ".env"]


class TestTerrariumStartupErrors:
    """Startup failures should surface the real error, not a generic root message."""

    def test_run_terrarium_with_tui_surfaces_start_exception(self):
        import asyncio

        from kohakuterrarium.terrarium.cli import run_terrarium_with_tui

        class FakeRuntime:
            is_running = False
            root_agent = None

            async def run(self):
                raise ValueError("API key not found")

        with pytest.raises(RuntimeError, match="API key not found"):
            asyncio.run(run_terrarium_with_tui(FakeRuntime()))
