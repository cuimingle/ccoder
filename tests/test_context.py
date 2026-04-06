"""Tests for system/user context construction."""
from __future__ import annotations
import pytest
from pathlib import Path
from app.context import build_system_prompt, load_claude_md


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prevent real ~/.claude/CLAUDE.md from leaking into tests."""
    fake_home = tmp_path / "_fakehome"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))


def test_build_system_prompt_contains_cwd(tmp_path: Path):
    prompt = build_system_prompt(cwd=str(tmp_path))
    assert str(tmp_path) in prompt


def test_build_system_prompt_contains_date(tmp_path: Path):
    prompt = build_system_prompt(cwd=str(tmp_path))
    import datetime
    assert str(datetime.date.today().year) in prompt


def test_load_claude_md_found(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Project\nDo things this way.")
    content = load_claude_md(str(tmp_path))
    assert "Do things this way." in content


def test_load_claude_md_not_found(tmp_path: Path):
    content = load_claude_md(str(tmp_path))
    assert content == ""


def test_build_system_prompt_includes_claude_md(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Custom Instructions\nAlways use snake_case.")
    prompt = build_system_prompt(cwd=str(tmp_path))
    assert "Always use snake_case." in prompt
