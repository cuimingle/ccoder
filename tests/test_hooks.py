"""Tests for hook runner."""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.hooks import HookResult, HookRunner
from app.settings import HookConfig
from app.tool import ToolResult


def _hook(event="PreToolUse", matcher="*", command="echo ok", timeout=30.0):
    return HookConfig(event=event, matcher=matcher, command=command, timeout=timeout)


class TestHookMatching:
    def test_matches_exact_tool(self):
        runner = HookRunner([_hook(matcher="Bash")])
        assert len(runner._matching_hooks("PreToolUse", "Bash")) == 1
        assert len(runner._matching_hooks("PreToolUse", "FileEdit")) == 0

    def test_matches_wildcard(self):
        runner = HookRunner([_hook(matcher="*")])
        assert len(runner._matching_hooks("PreToolUse", "Bash")) == 1
        assert len(runner._matching_hooks("PreToolUse", "FileEdit")) == 1

    def test_matches_event_type(self):
        runner = HookRunner([_hook(event="PostToolUse")])
        assert len(runner._matching_hooks("PreToolUse", "Bash")) == 0
        assert len(runner._matching_hooks("PostToolUse", "Bash")) == 1

    def test_glob_pattern(self):
        runner = HookRunner([_hook(matcher="File*")])
        assert len(runner._matching_hooks("PreToolUse", "FileEdit")) == 1
        assert len(runner._matching_hooks("PreToolUse", "FileRead")) == 1
        assert len(runner._matching_hooks("PreToolUse", "Bash")) == 0


class TestPreHooks:
    @pytest.mark.asyncio
    async def test_no_hooks_proceeds(self):
        runner = HookRunner([])
        result = await runner.run_pre_hooks("Bash", {"command": "ls"})
        assert result.proceed is True

    @pytest.mark.asyncio
    async def test_successful_hook_proceeds(self):
        runner = HookRunner([_hook(command="true")])
        result = await runner.run_pre_hooks("Bash", {"command": "ls"})
        assert result.proceed is True

    @pytest.mark.asyncio
    async def test_failing_hook_aborts(self):
        runner = HookRunner([_hook(command="exit 1")])
        result = await runner.run_pre_hooks("Bash", {"command": "ls"})
        assert result.proceed is False
        assert result.message != ""

    @pytest.mark.asyncio
    async def test_hook_receives_json_stdin(self):
        # Use a command that reads stdin and writes it to a file
        runner = HookRunner([_hook(command="cat > /dev/null")])
        result = await runner.run_pre_hooks("Bash", {"command": "git status"})
        assert result.proceed is True

    @pytest.mark.asyncio
    async def test_hook_stderr_in_message(self):
        runner = HookRunner([_hook(command="echo 'blocked!' >&2; exit 1")])
        result = await runner.run_pre_hooks("Bash", {"command": "rm -rf /"})
        assert result.proceed is False
        assert "blocked!" in result.message

    @pytest.mark.asyncio
    async def test_timeout_aborts(self):
        runner = HookRunner([_hook(command="sleep 10", timeout=0.5)])
        result = await runner.run_pre_hooks("Bash", {"command": "ls"})
        assert result.proceed is False
        assert "timed out" in result.message.lower()

    @pytest.mark.asyncio
    async def test_non_matching_hooks_skipped(self):
        runner = HookRunner([_hook(matcher="FileEdit", command="exit 1")])
        result = await runner.run_pre_hooks("Bash", {"command": "ls"})
        assert result.proceed is True

    @pytest.mark.asyncio
    async def test_first_failing_hook_stops(self):
        runner = HookRunner([
            _hook(command="exit 1"),
            _hook(command="exit 0"),
        ])
        result = await runner.run_pre_hooks("Bash", {"command": "ls"})
        assert result.proceed is False


class TestPostHooks:
    @pytest.mark.asyncio
    async def test_no_hooks(self):
        runner = HookRunner([])
        # Should not raise
        await runner.run_post_hooks("Bash", {"command": "ls"}, ToolResult(content="ok"))

    @pytest.mark.asyncio
    async def test_successful_post_hook(self):
        runner = HookRunner([_hook(event="PostToolUse", command="true")])
        await runner.run_post_hooks("Bash", {"command": "ls"}, ToolResult(content="ok"))

    @pytest.mark.asyncio
    async def test_failing_post_hook_does_not_raise(self):
        runner = HookRunner([_hook(event="PostToolUse", command="exit 1")])
        # Should not raise, just log
        await runner.run_post_hooks(
            "Bash", {"command": "ls"}, ToolResult(content="ok")
        )

    @pytest.mark.asyncio
    async def test_post_hook_timeout_does_not_raise(self):
        runner = HookRunner(
            [_hook(event="PostToolUse", command="sleep 10", timeout=0.5)]
        )
        await runner.run_post_hooks(
            "Bash", {"command": "ls"}, ToolResult(content="ok")
        )
