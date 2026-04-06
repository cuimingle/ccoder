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
        # Use a fake home to avoid reading real ~/.claude/settings.json
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
        # User settings
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git *)"]}})
        )
        monkeypatch.setattr("pathlib.Path.home", lambda: home)

        # Project settings
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
        # Project hooks override user hooks entirely
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
