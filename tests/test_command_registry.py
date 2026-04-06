"""Tests for CommandRegistry foundation."""
from __future__ import annotations

import pytest

from app.command_registry import (
    CommandRegistry,
    CommandResult,
    LocalCommand,
    PromptCommand,
)


class TestCommandResult:
    def test_defaults(self):
        result = CommandResult(text="hello")
        assert result.text == "hello"
        assert result.handled is True
        assert result.should_query is False
        assert result.prompt_content == ""


class TestCommandRegistry:
    def _make_registry(self) -> CommandRegistry:
        return CommandRegistry()

    def test_register_and_lookup(self):
        registry = self._make_registry()

        async def handler(args: str, context: dict) -> CommandResult:
            return CommandResult(text="ok")

        cmd = LocalCommand(name="test", description="A test command", handler=handler)
        registry.register(cmd)
        assert registry.get("test") is cmd

    def test_unknown_returns_none(self):
        registry = self._make_registry()
        assert registry.get("nonexistent") is None

    def test_prompt_command_type(self):
        async def get_prompt(args: str) -> str:
            return "prompt text"

        cmd = PromptCommand(
            name="review",
            description="Review code",
            get_prompt=get_prompt,
            progress_message="Reviewing...",
        )
        assert cmd.type == "prompt"
        assert cmd.name == "review"

    def test_local_command_type(self):
        async def handler(args: str, context: dict) -> CommandResult:
            return CommandResult(text="ok")

        cmd = LocalCommand(name="clear", description="Clear screen", handler=handler)
        assert cmd.type == "local"

    def test_list_commands_excludes_hidden(self):
        registry = self._make_registry()

        async def handler(args: str, context: dict) -> CommandResult:
            return CommandResult(text="ok")

        visible = LocalCommand(name="help", description="Show help", handler=handler)
        hidden = LocalCommand(
            name="debug", description="Debug info", handler=handler, is_hidden=True
        )
        registry.register(visible)
        registry.register(hidden)

        commands = registry.list_commands()
        names = [c.name for c in commands]
        assert "help" in names
        assert "debug" not in names

    def test_alias_lookup(self):
        registry = self._make_registry()

        async def handler(args: str, context: dict) -> CommandResult:
            return CommandResult(text="ok")

        cmd = LocalCommand(
            name="compact",
            description="Compact conversation",
            handler=handler,
            aliases=["c"],
        )
        registry.register(cmd)
        assert registry.get("compact") is cmd
        assert registry.get("c") is cmd

    @pytest.mark.asyncio
    async def test_execute_local_command(self):
        registry = self._make_registry()

        async def handler(args: str, context: dict) -> CommandResult:
            return CommandResult(text=f"executed with args={args}")

        cmd = LocalCommand(name="greet", description="Greet", handler=handler)
        registry.register(cmd)

        result = await registry.execute("greet", "world", {})
        assert result.text == "executed with args=world"
        assert result.handled is True
        assert result.should_query is False

    @pytest.mark.asyncio
    async def test_execute_prompt_command(self):
        registry = self._make_registry()

        async def get_prompt(args: str) -> str:
            return f"Please review: {args}"

        cmd = PromptCommand(
            name="review",
            description="Review code",
            get_prompt=get_prompt,
            progress_message="Reviewing...",
        )
        registry.register(cmd)

        result = await registry.execute("review", "main.py", {})
        assert result.should_query is True
        assert result.prompt_content == "Please review: main.py"
        assert result.handled is True

    @pytest.mark.asyncio
    async def test_execute_unknown_command(self):
        registry = self._make_registry()
        result = await registry.execute("unknown", "", {})
        assert result.handled is False
        assert "unknown" in result.text.lower() or "Unknown" in result.text
