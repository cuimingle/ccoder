"""Tests for permission checker."""
from __future__ import annotations

import os
import pytest
from app.permissions import PermissionChecker, validate_path, READ_ONLY_TOOLS
from app.settings import PermissionRule, Settings
from app.tool import ToolContext
from app.types.permissions import PermissionDecision, PermissionMode, PermissionResult


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))


def _settings(allow=None, deny=None):
    return Settings(
        permissions_allow=allow or [],
        permissions_deny=deny or [],
        hooks=[],
    )


class TestPlanMode:
    @pytest.mark.asyncio
    async def test_allows_readonly_tools(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.PLAN)
        for tool in READ_ONLY_TOOLS:
            decision = await checker.check(tool, {}, ctx)
            assert decision.result == PermissionResult.ALLOW, f"{tool} should be allowed"

    @pytest.mark.asyncio
    async def test_denies_write_tools(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.PLAN)
        for tool in ["Bash", "Edit", "Write", "FileEdit", "FileWrite"]:
            decision = await checker.check(tool, {}, ctx)
            assert decision.result == PermissionResult.DENY, f"{tool} should be denied"
            assert "plan mode" in decision.reason

    @pytest.mark.asyncio
    async def test_denies_bash(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.PLAN)
        decision = await checker.check("Bash", {"command": "ls"}, ctx)
        assert decision.result == PermissionResult.DENY


class TestAutoMode:
    @pytest.mark.asyncio
    async def test_allow_rule_matches(self, ctx):
        settings = _settings(allow=[PermissionRule(tool="Bash", pattern="git *")])
        checker = PermissionChecker(settings, PermissionMode.AUTO)
        decision = await checker.check("Bash", {"command": "git status"}, ctx)
        assert decision.result == PermissionResult.ALLOW

    @pytest.mark.asyncio
    async def test_deny_rule_matches(self, ctx):
        settings = _settings(deny=[PermissionRule(tool="Bash", pattern="rm -rf *")])
        checker = PermissionChecker(settings, PermissionMode.AUTO)
        decision = await checker.check("Bash", {"command": "rm -rf /"}, ctx)
        assert decision.result == PermissionResult.DENY

    @pytest.mark.asyncio
    async def test_deny_takes_precedence(self, ctx):
        settings = _settings(
            allow=[PermissionRule(tool="Bash", pattern="*")],
            deny=[PermissionRule(tool="Bash", pattern="rm *")],
        )
        checker = PermissionChecker(settings, PermissionMode.AUTO)
        decision = await checker.check("Bash", {"command": "rm file.txt"}, ctx)
        assert decision.result == PermissionResult.DENY

    @pytest.mark.asyncio
    async def test_no_match_denies(self, ctx):
        settings = _settings(allow=[PermissionRule(tool="Bash", pattern="git *")])
        checker = PermissionChecker(settings, PermissionMode.AUTO)
        decision = await checker.check("Bash", {"command": "ls"}, ctx)
        assert decision.result == PermissionResult.DENY
        assert "No allow rule" in decision.reason

    @pytest.mark.asyncio
    async def test_different_tool_not_matched(self, ctx):
        settings = _settings(allow=[PermissionRule(tool="Bash", pattern="*")])
        checker = PermissionChecker(settings, PermissionMode.AUTO)
        decision = await checker.check("FileEdit", {"file_path": "/tmp/x"}, ctx)
        assert decision.result == PermissionResult.DENY


class TestManualMode:
    @pytest.mark.asyncio
    async def test_deny_rule_blocks(self, ctx):
        settings = _settings(deny=[PermissionRule(tool="Bash", pattern="rm *")])
        checker = PermissionChecker(settings, PermissionMode.MANUAL)
        decision = await checker.check("Bash", {"command": "rm file"}, ctx)
        assert decision.result == PermissionResult.DENY

    @pytest.mark.asyncio
    async def test_no_match_asks_user(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.MANUAL)
        decision = await checker.check("Bash", {"command": "echo hi"}, ctx)
        assert decision.result == PermissionResult.ASK_USER

    @pytest.mark.asyncio
    async def test_allow_rule_matches(self, ctx):
        settings = _settings(allow=[PermissionRule(tool="Bash", pattern="git *")])
        checker = PermissionChecker(settings, PermissionMode.MANUAL)
        decision = await checker.check("Bash", {"command": "git status"}, ctx)
        assert decision.result == PermissionResult.ALLOW


class TestPathValidation:
    def test_normal_path_ok(self, tmp_path):
        (tmp_path / "file.txt").write_text("test")
        assert validate_path(str(tmp_path / "file.txt"), str(tmp_path)) is None

    def test_ssh_blocked(self, tmp_path):
        ssh_path = os.path.expanduser("~/.ssh/id_rsa")
        result = validate_path(ssh_path, str(tmp_path))
        assert result is not None
        assert "sensitive" in result

    def test_aws_blocked(self, tmp_path):
        aws_path = os.path.expanduser("~/.aws/credentials")
        result = validate_path(aws_path, str(tmp_path))
        assert result is not None
        assert "sensitive" in result

    def test_etc_blocked(self, tmp_path):
        result = validate_path("/etc/passwd", str(tmp_path))
        assert result is not None
        assert "sensitive" in result

    def test_empty_path_ok(self, tmp_path):
        assert validate_path("", str(tmp_path)) is None

    @pytest.mark.asyncio
    async def test_path_validation_in_checker(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.MANUAL)
        decision = await checker.check(
            "FileEdit",
            {"file_path": os.path.expanduser("~/.ssh/id_rsa")},
            ctx,
        )
        assert decision.result == PermissionResult.DENY
        assert "sensitive" in decision.reason


class TestSessionDecisions:
    @pytest.mark.asyncio
    async def test_allow_always(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.AUTO)
        # Initially denied (no allow rule)
        decision = await checker.check("Bash", {"command": "ls"}, ctx)
        assert decision.result == PermissionResult.DENY

        # Record allow_always
        checker.record_session_decision(
            "Bash", {"command": "ls"}, PermissionResult.ALLOW_ALWAYS
        )
        decision = await checker.check("Bash", {"command": "ls"}, ctx)
        assert decision.result == PermissionResult.ALLOW

    @pytest.mark.asyncio
    async def test_deny_always(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.MANUAL)
        # Initially ASK_USER (manual default, no matching rule)
        decision = await checker.check("Bash", {"command": "echo hi"}, ctx)
        assert decision.result == PermissionResult.ASK_USER

        # Record deny_always
        checker.record_session_decision(
            "Bash", {"command": "echo hi"}, PermissionResult.DENY_ALWAYS
        )
        decision = await checker.check("Bash", {"command": "echo hi"}, ctx)
        assert decision.result == PermissionResult.DENY
