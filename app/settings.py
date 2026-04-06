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

    event: str  # "PreToolUse" | "PostToolUse"
    matcher: str  # glob for tool name, e.g. "Bash" or "*"
    command: str  # shell command to run
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
    """Parse a list of rule strings, skipping invalid ones."""
    rules: list[PermissionRule] = []
    for item in raw:
        if isinstance(item, str):
            rule = parse_rule(item)
            if rule is not None:
                rules.append(rule)
    return rules


def _parse_hooks(raw: dict) -> list[HookConfig]:
    """Parse hooks section from settings JSON."""
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
                hooks.append(
                    HookConfig(
                        event=event_name,
                        matcher=matcher,
                        command=command,
                        timeout=float(timeout),
                    )
                )
    return hooks


def _load_single_file(path: Path) -> dict:
    """Load a single settings JSON file, returning empty dict on any error."""
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

    Merge strategy:
    - permissions.deny: union of both
    - permissions.allow: union of both
    - hooks: project overrides user (if project has hooks, user hooks are ignored)
    """
    home_path = Path.home() / ".claude" / "settings.json"
    project_path = Path(cwd) / ".claude" / "settings.json"

    user_data = _load_single_file(home_path)
    project_data = _load_single_file(project_path)

    # Parse permissions
    user_perms = user_data.get("permissions", {})
    project_perms = project_data.get("permissions", {})

    allow_rules = _parse_rules(user_perms.get("allow", []))
    allow_rules.extend(_parse_rules(project_perms.get("allow", [])))

    deny_rules = _parse_rules(user_perms.get("deny", []))
    deny_rules.extend(_parse_rules(project_perms.get("deny", [])))

    # Parse hooks — project overrides user
    hooks_data = project_data.get("hooks") or user_data.get("hooks") or {}
    hooks = _parse_hooks(hooks_data) if isinstance(hooks_data, dict) else []

    return Settings(
        permissions_allow=allow_rules,
        permissions_deny=deny_rules,
        hooks=hooks,
    )
