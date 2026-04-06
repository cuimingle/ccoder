"""Tests for tool executor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.tool_executor import ToolExecutor
from app.hooks import HookResult, HookRunner
from app.permissions import PermissionChecker
from app.tool import ToolContext, ToolResult
from app.types.permissions import PermissionDecision, PermissionResult


class FakeTool:
    """Minimal tool for testing."""

    name = "FakeTool"
    description = "A fake tool"
    readonly = False
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, result=None):
        self._result = result or ToolResult(content="fake result")
        self.called = False

    def is_enabled(self):
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        self.called = True
        return self._result

    def render_result(self, result: ToolResult) -> str:
        return result.content if isinstance(result.content, str) else str(result.content)


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        """Tool executes when permission allows and hooks pass."""
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(
            return_value=PermissionDecision(result=PermissionResult.ALLOW)
        )
        runner = MagicMock(spec=HookRunner)
        runner.run_pre_hooks = AsyncMock(return_value=HookResult())
        runner.run_post_hooks = AsyncMock()

        tool = FakeTool(ToolResult(content="success"))
        executor = ToolExecutor(checker, runner)
        result = await executor.execute(tool, {"key": "val"}, ctx)

        assert result.content == "success"
        assert result.is_error is False
        assert tool.called is True
        checker.check.assert_called_once()
        runner.run_pre_hooks.assert_called_once()
        runner.run_post_hooks.assert_called_once()

    @pytest.mark.asyncio
    async def test_permission_denied(self, ctx):
        """Tool does not execute when permission is denied."""
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(
            return_value=PermissionDecision(
                result=PermissionResult.DENY, reason="not allowed"
            )
        )
        runner = MagicMock(spec=HookRunner)

        tool = FakeTool()
        executor = ToolExecutor(checker, runner)
        result = await executor.execute(tool, {}, ctx)

        assert result.is_error is True
        assert "Permission denied" in result.content
        assert "not allowed" in result.content
        assert tool.called is False
        runner.run_pre_hooks.assert_not_called()

    @pytest.mark.asyncio
    async def test_hook_aborts(self, ctx):
        """Tool does not execute when pre-hook aborts."""
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(
            return_value=PermissionDecision(result=PermissionResult.ALLOW)
        )
        runner = MagicMock(spec=HookRunner)
        runner.run_pre_hooks = AsyncMock(
            return_value=HookResult(proceed=False, message="hook says no")
        )

        tool = FakeTool()
        executor = ToolExecutor(checker, runner)
        result = await executor.execute(tool, {}, ctx)

        assert result.is_error is True
        assert "Blocked by hook" in result.content
        assert tool.called is False

    @pytest.mark.asyncio
    async def test_tool_exception_caught(self, ctx):
        """Tool exceptions are caught and returned as error results."""
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(
            return_value=PermissionDecision(result=PermissionResult.ALLOW)
        )
        runner = MagicMock(spec=HookRunner)
        runner.run_pre_hooks = AsyncMock(return_value=HookResult())
        runner.run_post_hooks = AsyncMock()

        tool = FakeTool()
        tool.call = AsyncMock(side_effect=RuntimeError("boom"))

        executor = ToolExecutor(checker, runner)
        result = await executor.execute(tool, {}, ctx)

        assert result.is_error is True
        assert "boom" in result.content

    @pytest.mark.asyncio
    async def test_post_hooks_called_after_execution(self, ctx):
        """Post-hooks receive the tool result."""
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(
            return_value=PermissionDecision(result=PermissionResult.ALLOW)
        )
        runner = MagicMock(spec=HookRunner)
        runner.run_pre_hooks = AsyncMock(return_value=HookResult())
        runner.run_post_hooks = AsyncMock()

        tool_result = ToolResult(content="done")
        tool = FakeTool(tool_result)
        executor = ToolExecutor(checker, runner)
        await executor.execute(tool, {"x": 1}, ctx)

        runner.run_post_hooks.assert_called_once_with("FakeTool", {"x": 1}, tool_result)

    @pytest.mark.asyncio
    async def test_deny_always(self, ctx):
        """DENY_ALWAYS also blocks execution."""
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(
            return_value=PermissionDecision(
                result=PermissionResult.DENY_ALWAYS, reason="session deny"
            )
        )
        runner = MagicMock(spec=HookRunner)

        tool = FakeTool()
        executor = ToolExecutor(checker, runner)
        result = await executor.execute(tool, {}, ctx)

        assert result.is_error is True
        assert tool.called is False
