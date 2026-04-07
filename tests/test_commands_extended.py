"""Tests for extended slash commands (Phase 2+)."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from app.command_registry import CommandResult
from app.commands import build_default_registry


@pytest.fixture
def registry():
    return build_default_registry()


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.model = "claude-opus-4-6"
    engine.cwd = "/tmp/test"
    engine.permission_mode = "manual"
    engine.turn_count = 5
    engine.total_input_tokens = 10000
    engine.total_output_tokens = 5000
    engine.messages = []
    engine._tools = [MagicMock(), MagicMock()]
    engine._permission_checker = MagicMock()
    engine._permission_checker._settings = MagicMock()
    engine._permission_checker._settings.permissions_allow = []
    engine._permission_checker._settings.permissions_deny = []
    engine._permission_checker._settings.hooks = []
    engine._hook_runner = MagicMock()
    engine._hook_runner._hooks = []
    return engine


@pytest.fixture
def context(mock_engine, registry):
    return {
        "engine": mock_engine,
        "registry": registry,
        "total_input_tokens": 10000,
        "total_output_tokens": 5000,
        "turn_count": 5,
        "cwd": "/tmp/test",
        "app_state": MagicMock(),
    }


class TestExitCommand:
    @pytest.mark.asyncio
    async def test_exit_sets_should_exit(self, registry, context):
        result = await registry.execute("exit", "", context)
        assert result.should_exit is True
        assert result.handled is True

    @pytest.mark.asyncio
    async def test_quit_alias(self, registry, context):
        result = await registry.execute("quit", "", context)
        assert result.should_exit is True

    @pytest.mark.asyncio
    async def test_q_alias(self, registry, context):
        result = await registry.execute("q", "", context)
        assert result.should_exit is True


class TestModelCommand:
    @pytest.mark.asyncio
    async def test_model_display(self, registry, context):
        result = await registry.execute("model", "", context)
        assert "claude-opus-4-6" in result.text

    @pytest.mark.asyncio
    async def test_model_switch_alias(self, registry, context):
        result = await registry.execute("model", "sonnet", context)
        assert "claude-sonnet-4-6" in result.text
        assert context["engine"].model == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_model_switch_full_id(self, registry, context):
        result = await registry.execute("model", "my-custom-model", context)
        assert "my-custom-model" in result.text


class TestDiffCommand:
    @pytest.mark.asyncio
    async def test_diff_no_git(self, registry, context, tmp_path):
        context["cwd"] = str(tmp_path)
        result = await registry.execute("diff", "", context)
        # Either shows diff or an error
        assert result.handled is True


class TestExportCommand:
    @pytest.mark.asyncio
    async def test_export_empty(self, registry, context):
        context["engine"].messages = []
        result = await registry.execute("export", "", context)
        assert "No conversation" in result.text

    @pytest.mark.asyncio
    async def test_export_with_messages(self, registry, context, tmp_path):
        msg = MagicMock()
        msg.role = "user"
        msg.content = "hello"
        context["engine"].messages = [msg]
        context["cwd"] = str(tmp_path)
        result = await registry.execute("export", "test.md", context)
        assert "test.md" in result.text
        assert (tmp_path / "test.md").exists()


class TestRewindCommand:
    @pytest.mark.asyncio
    async def test_rewind_empty(self, registry, context):
        context["engine"].messages = []
        result = await registry.execute("rewind", "", context)
        assert "No messages" in result.text

    @pytest.mark.asyncio
    async def test_rewind_one(self, registry, context):
        user = MagicMock()
        user.role = "user"
        assistant = MagicMock()
        assistant.role = "assistant"
        context["engine"].messages = [user, assistant]
        context["engine"].turn_count = 1
        result = await registry.execute("rewind", "", context)
        assert "Rewound 1" in result.text
        assert len(context["engine"].messages) == 0

    @pytest.mark.asyncio
    async def test_rewind_invalid_count(self, registry, context):
        result = await registry.execute("rewind", "abc", context)
        assert "Invalid" in result.text


class TestInfoCommands:
    @pytest.mark.asyncio
    async def test_stats(self, registry, context):
        result = await registry.execute("stats", "", context)
        assert "Statistics" in result.text
        assert "10,000" in result.text

    @pytest.mark.asyncio
    async def test_status(self, registry, context):
        result = await registry.execute("status", "", context)
        assert "Status" in result.text
        assert "claude-opus-4-6" in result.text

    @pytest.mark.asyncio
    async def test_doctor(self, registry, context):
        result = await registry.execute("doctor", "", context)
        assert "Diagnostics" in result.text

    @pytest.mark.asyncio
    async def test_context_cmd(self, registry, context):
        result = await registry.execute("context", "", context)
        assert "Context" in result.text

    @pytest.mark.asyncio
    async def test_usage(self, registry, context):
        result = await registry.execute("usage", "", context)
        assert "Usage" in result.text


class TestConfigCommands:
    @pytest.mark.asyncio
    async def test_permissions(self, registry, context):
        result = await registry.execute("permissions", "", context)
        assert "Permission" in result.text

    @pytest.mark.asyncio
    async def test_hooks(self, registry, context):
        result = await registry.execute("hooks", "", context)
        assert result.handled is True

    @pytest.mark.asyncio
    async def test_config(self, registry, context):
        result = await registry.execute("config", "", context)
        assert "Configuration" in result.text


class TestEnvCommands:
    @pytest.mark.asyncio
    async def test_files_empty(self, registry, context):
        result = await registry.execute("files", "", context)
        assert "No files" in result.text

    @pytest.mark.asyncio
    async def test_add_dir_no_args(self, registry, context):
        result = await registry.execute("add-dir", "", context)
        assert "Usage" in result.text

    @pytest.mark.asyncio
    async def test_add_dir_valid(self, registry, context, tmp_path):
        result = await registry.execute("add-dir", str(tmp_path), context)
        assert "Added" in result.text or "noted" in result.text

    @pytest.mark.asyncio
    async def test_cwd_display(self, registry, context):
        result = await registry.execute("cwd", "", context)
        assert "/tmp/test" in result.text


class TestSessionCommands:
    @pytest.mark.asyncio
    async def test_session_save_empty(self, registry, context):
        context["engine"].messages = []
        result = await registry.execute("session", "", context)
        assert "No conversation" in result.text

    @pytest.mark.asyncio
    async def test_resume_list(self, registry, context):
        result = await registry.execute("resume", "", context)
        # Either lists sessions or says none found
        assert result.handled is True


class TestBranchCommand:
    @pytest.mark.asyncio
    async def test_branch_empty(self, registry, context):
        context["engine"].messages = []
        result = await registry.execute("branch", "", context)
        assert "No conversation" in result.text


class TestRenameCommand:
    @pytest.mark.asyncio
    async def test_rename_no_args(self, registry, context):
        result = await registry.execute("rename", "", context)
        assert "Usage" in result.text

    @pytest.mark.asyncio
    async def test_rename_with_name(self, registry, context):
        result = await registry.execute("rename", "my-session", context)
        assert "my-session" in result.text


class TestAllCommandsRegistered:
    """Verify that all expected commands are registered."""

    def test_command_count(self, registry):
        cmds = registry.list_commands()
        # At least 20 commands should be registered
        assert len(cmds) >= 20

    def test_known_commands_exist(self, registry):
        expected = [
            "clear", "compact", "exit", "model", "diff", "export",
            "session", "resume", "rewind", "branch", "rename",
            "cost", "help", "stats", "status", "doctor", "context", "usage",
            "permissions", "hooks", "config", "add-dir", "files", "cwd",
        ]
        for name in expected:
            assert registry.get(name) is not None, f"Command /{name} not registered"

    def test_aliases_work(self, registry):
        aliases = {
            "quit": "exit", "q": "exit", "h": "help", "?": "help",
            "continue": "resume", "fork": "branch",
            "allowed-tools": "permissions", "settings": "config",
        }
        for alias, expected_name in aliases.items():
            cmd = registry.get(alias)
            assert cmd is not None, f"Alias /{alias} not found"
            assert cmd.name == expected_name, f"/{alias} should resolve to /{expected_name}"
