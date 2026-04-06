# Claude Code Python — Phase 3: Permissions, Hooks & Compaction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现权限系统（plan/auto/manual 三模式）、Hook 系统（PreToolUse/PostToolUse shell 钩子）、会话压缩（auto-compact/micro-compact/API 摘要），并集成到工具执行流水线中。

**Architecture:** 在 `query.py` 的工具执行循环中注入 `ToolExecutor`，按 权限检查 → 预钩子 → 工具执行 → 后钩子 的流水线执行。Compaction 独立集成到 `QueryEngine`，在每轮结束后检查 token 阈值并自动压缩。

**Tech Stack:** Python 3.11+, `asyncio`, `fnmatch`, `json5`, `pathlib`, `subprocess`

---

## File Map

| 文件 | 职责 |
|------|------|
| `packages/app/settings.py` | 加载解析 `~/.claude/settings.json`，PermissionRule/HookConfig/Settings 数据类 |
| `packages/app/permissions.py` | PermissionChecker — PLAN/AUTO/MANUAL 模式权限检查 + 路径安全验证 |
| `packages/app/hooks.py` | HookRunner — PreToolUse/PostToolUse shell 命令钩子执行 |
| `packages/app/tool_executor.py` | ToolExecutor — 权限→预钩子→工具执行→后钩子 流水线编排 |
| `packages/app/compaction.py` | 会话压缩 — auto-compact、micro-compact、API 摘要 |
| `packages/app/commands.py` | 斜杠命令解析器（/compact、/clear） |
| `packages/app/query.py` | 修改：接受可选 `tool_executor` 参数 |
| `packages/app/query_engine.py` | 修改：构建 ToolExecutor、自动压缩、斜杠命令路由 |
| `packages/app/tools/*.py` | 修改：每个工具添加 `readonly` 属性 |
| `tests/test_settings.py` | Settings 加载/解析测试 |
| `tests/test_permissions.py` | 权限检查测试 |
| `tests/test_hooks.py` | Hook 执行测试 |
| `tests/test_tool_executor.py` | ToolExecutor 集成测试 |
| `tests/test_compaction.py` | 压缩逻辑测试 |
| `tests/test_commands.py` | 斜杠命令测试 |

---

## Task 15: Settings Loader

**Files:**
- Create: `packages/app/settings.py`
- Create: `tests/test_settings.py`

- [x] **Step 1: 写测试 tests/test_settings.py**

```python
"""Tests for settings loader."""
from __future__ import annotations

import json
import pytest
from app.settings import (
    HookConfig,
    PermissionRule,
    Settings,
    load_settings,
    parse_rule,
)


class TestParseRule:
    def test_valid_rule(self):
        rule = parse_rule("Bash(git *)")
        assert rule == PermissionRule(tool="Bash", pattern="git *")

    def test_valid_rule_with_path(self):
        rule = parse_rule("FileEdit(/home/user/project/*)")
        assert rule == PermissionRule(tool="FileEdit", pattern="/home/user/project/*")

    def test_invalid_rule_no_parens(self):
        assert parse_rule("Bash") is None

    def test_invalid_rule_empty(self):
        assert parse_rule("") is None

    def test_invalid_rule_bad_format(self):
        assert parse_rule("(git *)") is None

    def test_rule_with_spaces(self):
        rule = parse_rule("  Bash(rm -rf *)  ")
        assert rule == PermissionRule(tool="Bash", pattern="rm -rf *")


class TestLoadSettings:
    def test_missing_files_returns_empty(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
        settings = load_settings(str(tmp_path / "nonexistent"))
        assert settings == Settings()

    def test_user_settings_only(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "permissions": {
                        "allow": ["Bash(git *)"],
                        "deny": ["Bash(rm -rf *)"],
                    }
                }
            )
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: home)

        settings = load_settings(str(tmp_path))
        assert len(settings.permissions_allow) == 1
        assert settings.permissions_allow[0].tool == "Bash"
        assert settings.permissions_allow[0].pattern == "git *"
        assert len(settings.permissions_deny) == 1
        assert settings.permissions_deny[0].pattern == "rm -rf *"

    def test_project_settings_merge(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git *)"]}})
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: home)

        proj_claude = tmp_path / ".claude"
        proj_claude.mkdir()
        (proj_claude / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["FileEdit(/src/*)"], "deny": ["Bash(rm *)"]}})
        )

        settings = load_settings(str(tmp_path))
        assert len(settings.permissions_allow) == 2  # merged
        assert len(settings.permissions_deny) == 1

    def test_hooks_from_user(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [{"type": "command", "command": "echo pre"}],
                            }
                        ]
                    }
                }
            )
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: home)

        settings = load_settings(str(tmp_path))
        assert len(settings.hooks) == 1
        assert settings.hooks[0].event == "PreToolUse"
        assert settings.hooks[0].matcher == "Bash"
        assert settings.hooks[0].command == "echo pre"

    def test_hooks_project_overrides_user(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {"matcher": "*", "hooks": [{"type": "command", "command": "echo user"}]}
                        ]
                    }
                }
            )
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: home)

        proj_claude = tmp_path / ".claude"
        proj_claude.mkdir()
        (proj_claude / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PostToolUse": [
                            {"matcher": "*", "hooks": [{"type": "command", "command": "echo project"}]}
                        ]
                    }
                }
            )
        )

        settings = load_settings(str(tmp_path))
        assert len(settings.hooks) == 1
        assert settings.hooks[0].event == "PostToolUse"
        assert settings.hooks[0].command == "echo project"

    def test_malformed_json_returns_empty(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text("{invalid json")
        monkeypatch.setattr("pathlib.Path.home", lambda: home)

        settings = load_settings(str(tmp_path))
        assert settings == Settings()

    def test_invalid_rules_skipped(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "permissions": {
                        "allow": ["valid_rule_nope", "Bash(git *)", 123, None],
                    }
                }
            )
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: home)

        settings = load_settings(str(tmp_path))
        assert len(settings.permissions_allow) == 1

    def test_hook_timeout_custom(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {"type": "command", "command": "echo x", "timeout": 10}
                                ],
                            }
                        ]
                    }
                }
            )
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: home)

        settings = load_settings(str(tmp_path))
        assert settings.hooks[0].timeout == 10.0
```

- [x] **Step 2: 实现 packages/app/settings.py**

```python
"""Settings loader — parses ~/.claude/settings.json and project-level overrides."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import json5


@dataclass
class PermissionRule:
    """A single permission rule, e.g. Bash(git *)."""
    tool: str
    pattern: str


@dataclass
class HookConfig:
    """A single hook entry from settings."""
    event: str      # "PreToolUse" | "PostToolUse"
    matcher: str    # glob for tool name, e.g. "Bash" or "*"
    command: str    # shell command to run
    timeout: float = 30.0


@dataclass
class Settings:
    """Merged settings from user and project config."""
    permissions_allow: list[PermissionRule] = field(default_factory=list)
    permissions_deny: list[PermissionRule] = field(default_factory=list)
    hooks: list[HookConfig] = field(default_factory=list)


_RULE_PATTERN = re.compile(r"^(\w+)\((.+)\)$")


def parse_rule(rule_str: str) -> PermissionRule | None:
    """Parse 'ToolName(pattern)' into a PermissionRule, or None if invalid."""
    m = _RULE_PATTERN.match(rule_str.strip())
    if not m:
        return None
    return PermissionRule(tool=m.group(1), pattern=m.group(2))


def _parse_rules(raw: list) -> list[PermissionRule]:
    rules: list[PermissionRule] = []
    for item in raw:
        if isinstance(item, str):
            rule = parse_rule(item)
            if rule is not None:
                rules.append(rule)
    return rules


def _parse_hooks(raw: dict) -> list[HookConfig]:
    hooks: list[HookConfig] = []
    for event_name, matchers in raw.items():
        if not isinstance(matchers, list):
            continue
        for entry in matchers:
            if not isinstance(entry, dict):
                continue
            matcher = entry.get("matcher", "*")
            hook_list = entry.get("hooks", [])
            if not isinstance(hook_list, list):
                continue
            for hook in hook_list:
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command")
                if not command:
                    continue
                timeout = hook.get("timeout", 30.0)
                hooks.append(HookConfig(
                    event=event_name, matcher=matcher,
                    command=command, timeout=float(timeout),
                ))
    return hooks


def _load_single_file(path: Path) -> dict:
    try:
        if not path.is_file():
            return {}
        text = path.read_text(encoding="utf-8")
        data = json5.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_settings(cwd: str) -> Settings:
    """
    Load and merge settings from ~/.claude/settings.json and {cwd}/.claude/settings.json.
    Merge: permissions union, hooks project overrides user.
    """
    home_path = Path.home() / ".claude" / "settings.json"
    project_path = Path(cwd) / ".claude" / "settings.json"

    user_data = _load_single_file(home_path)
    project_data = _load_single_file(project_path)

    user_perms = user_data.get("permissions", {})
    project_perms = project_data.get("permissions", {})

    allow_rules = _parse_rules(user_perms.get("allow", []))
    allow_rules.extend(_parse_rules(project_perms.get("allow", [])))
    deny_rules = _parse_rules(user_perms.get("deny", []))
    deny_rules.extend(_parse_rules(project_perms.get("deny", [])))

    hooks_data = project_data.get("hooks") or user_data.get("hooks") or {}
    hooks = _parse_hooks(hooks_data) if isinstance(hooks_data, dict) else []

    return Settings(permissions_allow=allow_rules, permissions_deny=deny_rules, hooks=hooks)
```

- [x] **Step 3: 运行测试确认通过**

---

## Task 16: Permission Checker

**Files:**
- Create: `packages/app/permissions.py`
- Create: `tests/test_permissions.py`

- [x] **Step 1: 写测试 tests/test_permissions.py**

```python
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
    return Settings(permissions_allow=allow or [], permissions_deny=deny or [], hooks=[])


class TestPlanMode:
    @pytest.mark.asyncio
    async def test_allows_readonly_tools(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.PLAN)
        for tool in READ_ONLY_TOOLS:
            decision = await checker.check(tool, {}, ctx)
            assert decision.result == PermissionResult.ALLOW

    @pytest.mark.asyncio
    async def test_denies_write_tools(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.PLAN)
        for tool in ["Bash", "Edit", "Write", "FileEdit", "FileWrite"]:
            decision = await checker.check(tool, {}, ctx)
            assert decision.result == PermissionResult.DENY
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


class TestManualMode:
    @pytest.mark.asyncio
    async def test_deny_rule_blocks(self, ctx):
        settings = _settings(deny=[PermissionRule(tool="Bash", pattern="rm *")])
        checker = PermissionChecker(settings, PermissionMode.MANUAL)
        decision = await checker.check("Bash", {"command": "rm file"}, ctx)
        assert decision.result == PermissionResult.DENY

    @pytest.mark.asyncio
    async def test_no_match_allows(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.MANUAL)
        decision = await checker.check("Bash", {"command": "echo hi"}, ctx)
        assert decision.result == PermissionResult.ALLOW


class TestPathValidation:
    def test_ssh_blocked(self, tmp_path):
        result = validate_path(os.path.expanduser("~/.ssh/id_rsa"), str(tmp_path))
        assert result is not None and "sensitive" in result

    def test_etc_blocked(self, tmp_path):
        result = validate_path("/etc/passwd", str(tmp_path))
        assert result is not None and "sensitive" in result

    def test_empty_path_ok(self, tmp_path):
        assert validate_path("", str(tmp_path)) is None


class TestSessionDecisions:
    @pytest.mark.asyncio
    async def test_allow_always(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.AUTO)
        decision = await checker.check("Bash", {"command": "ls"}, ctx)
        assert decision.result == PermissionResult.DENY
        checker.record_session_decision("Bash", {"command": "ls"}, PermissionResult.ALLOW_ALWAYS)
        decision = await checker.check("Bash", {"command": "ls"}, ctx)
        assert decision.result == PermissionResult.ALLOW

    @pytest.mark.asyncio
    async def test_deny_always(self, ctx):
        checker = PermissionChecker(_settings(), PermissionMode.MANUAL)
        decision = await checker.check("Bash", {"command": "echo hi"}, ctx)
        assert decision.result == PermissionResult.ALLOW
        checker.record_session_decision("Bash", {"command": "echo hi"}, PermissionResult.DENY_ALWAYS)
        decision = await checker.check("Bash", {"command": "echo hi"}, ctx)
        assert decision.result == PermissionResult.DENY
```

- [x] **Step 2: 实现 packages/app/permissions.py**

```python
"""Permission checker — mode-based allow/deny with path validation."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from app.settings import Settings, PermissionRule
from app.tool import ToolContext
from app.types.permissions import PermissionDecision, PermissionMode, PermissionResult

READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob", "TaskList", "TaskGet"})

SENSITIVE_PATHS = (
    os.path.expanduser("~/.ssh"),
    os.path.expanduser("~/.aws"),
    os.path.expanduser("~/.gnupg"),
    "/etc",
)


def _get_tool_input_summary(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Bash":
        return tool_input.get("command", "")
    if tool_name in ("Read", "Edit", "Write", "FileRead", "FileEdit", "FileWrite"):
        return tool_input.get("file_path", "")
    if tool_name in ("Grep", "Glob"):
        return tool_input.get("pattern", "")
    return str(tool_input)


def _matches_rule(rule: PermissionRule, tool_name: str, input_summary: str) -> bool:
    if not fnmatch.fnmatch(tool_name, rule.tool):
        return False
    return fnmatch.fnmatch(input_summary, rule.pattern)


def validate_path(file_path: str, cwd: str) -> str | None:
    if not file_path:
        return None
    try:
        resolved = Path(file_path).resolve()
    except (ValueError, OSError):
        return f"Invalid path: {file_path}"

    resolved_str = str(resolved)
    for sensitive in SENSITIVE_PATHS:
        try:
            sensitive_resolved = str(Path(sensitive).resolve())
            if resolved_str.startswith(sensitive_resolved):
                return f"Access denied: {file_path} is in a sensitive directory"
        except (ValueError, OSError):
            continue
    return None


class PermissionChecker:
    def __init__(self, settings: Settings, mode: PermissionMode):
        self.settings = settings
        self.mode = mode
        self._session_allow: set[str] = set()
        self._session_deny: set[str] = set()

    async def check(self, tool_name: str, tool_input: dict, context: ToolContext) -> PermissionDecision:
        # Path validation
        file_path = tool_input.get("file_path", "")
        if file_path:
            path_error = validate_path(file_path, context.cwd)
            if path_error:
                return PermissionDecision(result=PermissionResult.DENY, reason=path_error)

        # Session overrides
        session_key = f"{tool_name}:{_get_tool_input_summary(tool_name, tool_input)}"
        if session_key in self._session_deny:
            return PermissionDecision(result=PermissionResult.DENY, reason="Denied for this session")
        if session_key in self._session_allow:
            return PermissionDecision(result=PermissionResult.ALLOW)

        # Mode dispatch
        if self.mode == PermissionMode.PLAN:
            return self._check_plan_mode(tool_name)
        elif self.mode == PermissionMode.AUTO:
            return self._check_auto_mode(tool_name, tool_input)
        else:
            return self._check_manual_mode(tool_name, tool_input)

    def _check_plan_mode(self, tool_name: str) -> PermissionDecision:
        if tool_name in READ_ONLY_TOOLS:
            return PermissionDecision(result=PermissionResult.ALLOW)
        return PermissionDecision(result=PermissionResult.DENY,
            reason=f"Tool '{tool_name}' is not allowed in plan mode (read-only)")

    def _check_auto_mode(self, tool_name: str, tool_input: dict) -> PermissionDecision:
        input_summary = _get_tool_input_summary(tool_name, tool_input)
        for rule in self.settings.permissions_deny:
            if _matches_rule(rule, tool_name, input_summary):
                return PermissionDecision(result=PermissionResult.DENY,
                    reason=f"Matched deny rule: {rule.tool}({rule.pattern})")
        for rule in self.settings.permissions_allow:
            if _matches_rule(rule, tool_name, input_summary):
                return PermissionDecision(result=PermissionResult.ALLOW)
        return PermissionDecision(result=PermissionResult.DENY,
            reason=f"No allow rule matches {tool_name} in auto mode")

    def _check_manual_mode(self, tool_name: str, tool_input: dict) -> PermissionDecision:
        input_summary = _get_tool_input_summary(tool_name, tool_input)
        for rule in self.settings.permissions_deny:
            if _matches_rule(rule, tool_name, input_summary):
                return PermissionDecision(result=PermissionResult.DENY,
                    reason=f"Matched deny rule: {rule.tool}({rule.pattern})")
        for rule in self.settings.permissions_allow:
            if _matches_rule(rule, tool_name, input_summary):
                return PermissionDecision(result=PermissionResult.ALLOW)
        return PermissionDecision(result=PermissionResult.ALLOW)

    def record_session_decision(self, tool_name: str, tool_input: dict, result: PermissionResult) -> None:
        session_key = f"{tool_name}:{_get_tool_input_summary(tool_name, tool_input)}"
        if result == PermissionResult.ALLOW_ALWAYS:
            self._session_allow.add(session_key)
            self._session_deny.discard(session_key)
        elif result == PermissionResult.DENY_ALWAYS:
            self._session_deny.add(session_key)
            self._session_allow.discard(session_key)
```

- [x] **Step 3: 运行测试确认通过**

---

## Task 17: Hook Runner

**Files:**
- Create: `packages/app/hooks.py`
- Create: `tests/test_hooks.py`

- [x] **Step 1: 写测试 tests/test_hooks.py**

```python
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

    def test_glob_pattern(self):
        runner = HookRunner([_hook(matcher="File*")])
        assert len(runner._matching_hooks("PreToolUse", "FileEdit")) == 1
        assert len(runner._matching_hooks("PreToolUse", "Bash")) == 0


class TestPreHooks:
    @pytest.mark.asyncio
    async def test_no_hooks_proceeds(self):
        runner = HookRunner([])
        result = await runner.run_pre_hooks("Bash", {"command": "ls"})
        assert result.proceed is True

    @pytest.mark.asyncio
    async def test_failing_hook_aborts(self):
        runner = HookRunner([_hook(command="exit 1")])
        result = await runner.run_pre_hooks("Bash", {"command": "ls"})
        assert result.proceed is False

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


class TestPostHooks:
    @pytest.mark.asyncio
    async def test_failing_post_hook_does_not_raise(self):
        runner = HookRunner([_hook(event="PostToolUse", command="exit 1")])
        await runner.run_post_hooks("Bash", {"command": "ls"}, ToolResult(content="ok"))
```

- [x] **Step 2: 实现 packages/app/hooks.py**

```python
"""Hook runner — execute shell hooks before/after tool calls."""
from __future__ import annotations

import asyncio
import json
import fnmatch
import logging
from dataclasses import dataclass

from app.settings import HookConfig
from app.tool import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class HookResult:
    proceed: bool = True
    message: str = ""


class HookRunner:
    def __init__(self, hooks: list[HookConfig]):
        self._hooks = hooks

    def _matching_hooks(self, event: str, tool_name: str) -> list[HookConfig]:
        return [h for h in self._hooks
                if h.event == event and fnmatch.fnmatch(tool_name, h.matcher)]

    async def _run_hook_command(self, hook: HookConfig, stdin_data: dict) -> tuple[int, str, str]:
        stdin_bytes = json.dumps(stdin_data, default=str).encode("utf-8")
        proc = await asyncio.create_subprocess_shell(
            hook.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes), timeout=hook.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", f"Hook timed out after {hook.timeout}s: {hook.command}"
        return (proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"))

    async def run_pre_hooks(self, tool_name: str, tool_input: dict) -> HookResult:
        hooks = self._matching_hooks("PreToolUse", tool_name)
        if not hooks:
            return HookResult()
        stdin_data = {"tool_name": tool_name, "tool_input": tool_input}
        for hook in hooks:
            returncode, stdout, stderr = await self._run_hook_command(hook, stdin_data)
            if returncode != 0:
                message = stderr.strip() or stdout.strip() or f"Hook exited with code {returncode}"
                return HookResult(proceed=False, message=message)
        return HookResult()

    async def run_post_hooks(self, tool_name: str, tool_input: dict, tool_result: ToolResult) -> None:
        hooks = self._matching_hooks("PostToolUse", tool_name)
        if not hooks:
            return
        result_content = tool_result.content if isinstance(tool_result.content, str) else str(tool_result.content)
        stdin_data = {"tool_name": tool_name, "tool_input": tool_input,
                      "tool_result": {"content": result_content[:5000], "is_error": tool_result.is_error}}
        for hook in hooks:
            try:
                returncode, stdout, stderr = await self._run_hook_command(hook, stdin_data)
                if returncode != 0:
                    logger.warning("PostToolUse hook failed (rc=%d): %s", returncode, hook.command)
            except Exception as e:
                logger.warning("PostToolUse hook error: %s — %s", hook.command, e)
```

- [x] **Step 3: 运行测试确认通过**

---

## Task 18: Tool Executor + Integration

**Files:**
- Create: `packages/app/tool_executor.py`
- Create: `tests/test_tool_executor.py`
- Modify: `packages/app/query.py`
- Modify: `packages/app/query_engine.py`
- Modify: `packages/app/tools/*.py` (添加 `readonly` 属性)

- [x] **Step 1: 写测试 tests/test_tool_executor.py**

```python
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
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(return_value=PermissionDecision(result=PermissionResult.ALLOW))
        runner = MagicMock(spec=HookRunner)
        runner.run_pre_hooks = AsyncMock(return_value=HookResult())
        runner.run_post_hooks = AsyncMock()

        tool = FakeTool(ToolResult(content="success"))
        executor = ToolExecutor(checker, runner)
        result = await executor.execute(tool, {"key": "val"}, ctx)
        assert result.content == "success"
        assert tool.called is True

    @pytest.mark.asyncio
    async def test_permission_denied(self, ctx):
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(return_value=PermissionDecision(
            result=PermissionResult.DENY, reason="not allowed"))
        runner = MagicMock(spec=HookRunner)
        tool = FakeTool()
        executor = ToolExecutor(checker, runner)
        result = await executor.execute(tool, {}, ctx)
        assert result.is_error is True
        assert "Permission denied" in result.content
        assert tool.called is False

    @pytest.mark.asyncio
    async def test_hook_aborts(self, ctx):
        checker = MagicMock(spec=PermissionChecker)
        checker.check = AsyncMock(return_value=PermissionDecision(result=PermissionResult.ALLOW))
        runner = MagicMock(spec=HookRunner)
        runner.run_pre_hooks = AsyncMock(return_value=HookResult(proceed=False, message="hook says no"))
        tool = FakeTool()
        executor = ToolExecutor(checker, runner)
        result = await executor.execute(tool, {}, ctx)
        assert result.is_error is True
        assert "Blocked by hook" in result.content
        assert tool.called is False
```

- [x] **Step 2: 实现 packages/app/tool_executor.py**

```python
"""Tool executor — orchestrates permission check, hooks, and tool execution."""
from __future__ import annotations

from app.hooks import HookRunner
from app.permissions import PermissionChecker
from app.tool import Tool, ToolContext, ToolResult
from app.types.permissions import PermissionResult


class ToolExecutor:
    def __init__(self, permission_checker: PermissionChecker, hook_runner: HookRunner):
        self.permission_checker = permission_checker
        self.hook_runner = hook_runner

    async def execute(self, tool: Tool, tool_input: dict, context: ToolContext) -> ToolResult:
        # 1. Permission check
        decision = await self.permission_checker.check(tool.name, tool_input, context)
        if decision.result in (PermissionResult.DENY, PermissionResult.DENY_ALWAYS):
            return ToolResult(content=f"Permission denied: {decision.reason}", is_error=True)

        # 2. Pre-hooks
        hook_result = await self.hook_runner.run_pre_hooks(tool.name, tool_input)
        if not hook_result.proceed:
            return ToolResult(content=f"Blocked by hook: {hook_result.message}", is_error=True)

        # 3. Execute tool
        try:
            result = await tool.call(tool_input, context)
        except Exception as e:
            result = ToolResult(content=str(e), is_error=True)

        # 4. Post-hooks
        await self.hook_runner.run_post_hooks(tool.name, tool_input, result)
        return result
```

- [x] **Step 3: 修改 query.py — 接受可选 tool_executor 参数**

在 `query()` 签名中添加 `tool_executor: "ToolExecutor | None" = None`，在工具执行循环中，如果有 executor 则调用 `tool_executor.execute()`，否则直接 `tool.call()`（向后兼容）。

- [x] **Step 4: 修改 query_engine.py — 构建 ToolExecutor 并传入 query()**

QueryEngine.__init__ 中加载 Settings、创建 PermissionChecker、HookRunner、ToolExecutor，run_turn() 将 tool_executor 传入 query()。

- [x] **Step 5: 给 15 个工具添加 readonly 属性**

`readonly = True`: FileReadTool, GrepTool, GlobTool, TaskListTool, TaskGetTool
`readonly = False`: 其余 10 个工具

- [x] **Step 6: 运行全部测试确认通过**

---

## Task 19: Compaction System

**Files:**
- Create: `packages/app/compaction.py`
- Create: `tests/test_compaction.py`

- [x] **Step 1: 写测试 tests/test_compaction.py**

```python
"""Tests for compaction system."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.compaction import (
    COMPACT_THRESHOLD, CONTEXT_WINDOW, MAX_TOOL_RESULT_CHARS, TRUNCATED_KEEP_CHARS,
    compact_conversation, micro_compact_message, micro_compact_messages, should_compact,
)
from app.types.message import (
    AssistantMessage, TextBlock, ToolResultBlock, UserMessage,
)
from app.services.api.claude import StreamEvent


class TestShouldCompact:
    def test_below_threshold(self):
        assert should_compact(100_000) is False

    def test_at_threshold(self):
        tokens = int(CONTEXT_WINDOW * COMPACT_THRESHOLD) + 1
        assert should_compact(tokens) is True


class TestMicroCompact:
    def test_short_content_unchanged(self):
        msg = UserMessage(content=[ToolResultBlock(tool_use_id="1", content="short", is_error=False)])
        result = micro_compact_message(msg)
        assert result is msg

    def test_long_content_truncated(self):
        long_content = "x" * (MAX_TOOL_RESULT_CHARS + 1000)
        msg = UserMessage(content=[ToolResultBlock(tool_use_id="1", content=long_content, is_error=False)])
        result = micro_compact_message(msg)
        assert "[... truncated ...]" in result.content[0].content


class TestCompactConversation:
    @pytest.fixture
    def mock_api_client(self):
        client = MagicMock()
        async def mock_stream(params):
            yield StreamEvent(type="text_delta", text="Summary of conversation.")
            yield StreamEvent(type="usage", input_tokens=500, output_tokens=100)
            yield StreamEvent(type="message_stop")
        client.stream = mock_stream
        client.build_request_params = MagicMock(return_value=MagicMock())
        return client

    @pytest.mark.asyncio
    async def test_compact_replaces_history(self, mock_api_client):
        messages = [
            UserMessage(content="first question"),
            AssistantMessage(content=[TextBlock(text="first answer")]),
            UserMessage(content="second question"),
        ]
        new_msgs, in_tokens, out_tokens = await compact_conversation(messages, mock_api_client, "system")
        assert len(new_msgs) == 2
        assert "[Previous conversation summary]" in new_msgs[0].content
        assert new_msgs[1].content == "second question"
        assert in_tokens == 500
```

- [x] **Step 2: 实现 packages/app/compaction.py**

核心功能：
- `should_compact(total_input_tokens)` — 检查是否超过 90% 上下文窗口
- `micro_compact_message(message)` — 截断 >10K 字符的 ToolResultBlock（保留首尾 2K）
- `compact_conversation(messages, api_client, system)` — 调用 API 生成摘要替换历史

- [x] **Step 3: 运行测试确认通过**

---

## Task 20: /compact Command

**Files:**
- Create: `packages/app/commands.py`
- Create: `tests/test_commands.py`
- Modify: `packages/app/query_engine.py`

- [x] **Step 1: 写测试 tests/test_commands.py**

```python
"""Tests for slash command dispatcher."""
from __future__ import annotations

from app.commands import is_command, parse_command


class TestParseCommand:
    def test_valid_command(self):
        result = parse_command("/compact")
        assert result == ("compact", "")

    def test_command_with_args(self):
        result = parse_command("/compact summary")
        assert result == ("compact", "summary")

    def test_not_a_command(self):
        assert parse_command("hello world") is None

    def test_empty_string(self):
        assert parse_command("") is None


class TestIsCommand:
    def test_is_command(self):
        assert is_command("/compact") is True

    def test_not_command(self):
        assert is_command("hello") is False
```

- [x] **Step 2: 实现 packages/app/commands.py**

```python
"""Slash command dispatcher for /compact and other commands."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CommandResult:
    text: str
    handled: bool = True


def parse_command(user_input: str) -> tuple[str, str] | None:
    stripped = user_input.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.split(None, 1)
    command = parts[0][1:]
    args = parts[1] if len(parts) > 1 else ""
    return command, args


KNOWN_COMMANDS = {"compact", "clear", "help"}


def is_command(user_input: str) -> bool:
    return parse_command(user_input) is not None
```

- [x] **Step 3: 修改 query_engine.py — 路由 /compact 和 /clear 命令**

在 `run_turn()` 开头检查 `parse_command(user_input)`，若为 `/compact` 则调用 `self.compact()`，若为 `/clear` 则重置会话。同时在 `run_turn()` 结尾添加 `should_compact()` 检查和自动压缩。

- [x] **Step 4: 运行全部测试确认通过**

---

## Task Dependency Graph

```
Task 15 (Settings)──────┬──> Task 16 (Permissions)──┐
                        ├──> Task 17 (Hooks)─────────┤
                        │                            v
                        │                   Task 18 (Executor + Integration)
                        │
Task 19 (Compaction)────┬──> Task 20 (/compact)
```

并行轨道：Tasks 15+19 先行，然后 16+17 并行，最后 18 和 20。

---

## Verification

1. **单元测试:** `uv run pytest tests/test_settings.py tests/test_permissions.py tests/test_hooks.py tests/test_tool_executor.py tests/test_compaction.py tests/test_commands.py -v`
2. **全量测试:** `uv run pytest -v`（无回归）
3. **Pipe 模式 e2e:** `echo "list files in current dir" | uv run python -m app -p`
4. **权限拒绝:** 设置 plan 模式，验证写工具返回 permission denied
