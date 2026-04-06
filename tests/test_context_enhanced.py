"""Tests for multi-level CLAUDE.md loading."""
from __future__ import annotations

import pytest
from pathlib import Path

from app.context import (
    build_system_prompt,
    load_claude_md,
    load_claude_md_hierarchy,
)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Ensure tests don't pick up real user ~/.claude/CLAUDE.md."""
    fake_home = tmp_path / "_fakehome"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))


def test_load_cwd_claude_md(tmp_path: Path):
    """CLAUDE.md at cwd root is loaded."""
    (tmp_path / "CLAUDE.md").write_text("root instructions")
    result = load_claude_md_hierarchy(str(tmp_path))
    assert any("root instructions" in content for _, content in result)


def test_load_project_level_claude_md(tmp_path: Path):
    """.claude/CLAUDE.md is loaded."""
    dot_claude = tmp_path / ".claude"
    dot_claude.mkdir()
    (dot_claude / "CLAUDE.md").write_text("project dot-claude instructions")
    result = load_claude_md_hierarchy(str(tmp_path))
    assert any("project dot-claude instructions" in content for _, content in result)


def test_load_both_project_and_cwd(tmp_path: Path):
    """Both .claude/CLAUDE.md and CLAUDE.md are loaded; no duplicates."""
    dot_claude = tmp_path / ".claude"
    dot_claude.mkdir()
    (dot_claude / "CLAUDE.md").write_text("from dot-claude")
    (tmp_path / "CLAUDE.md").write_text("from root")
    result = load_claude_md_hierarchy(str(tmp_path))
    contents = [content for _, content in result]
    assert "from dot-claude" in " ".join(contents)
    assert "from root" in " ".join(contents)
    # Should have exactly 2 entries (no user global in this test)
    assert len(result) == 2


def test_load_both_dedup_symlink(tmp_path: Path):
    """If .claude/CLAUDE.md is a symlink to CLAUDE.md, only load once."""
    (tmp_path / "CLAUDE.md").write_text("shared instructions")
    dot_claude = tmp_path / ".claude"
    dot_claude.mkdir()
    (dot_claude / "CLAUDE.md").symlink_to(tmp_path / "CLAUDE.md")
    result = load_claude_md_hierarchy(str(tmp_path))
    assert len(result) == 1


def test_load_user_global_claude_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """User global ~/.claude/CLAUDE.md is loaded."""
    # _isolate_home sets HOME to tmp_path/_fakehome
    fake_home = tmp_path / "_fakehome"
    user_claude_dir = fake_home / ".claude"
    user_claude_dir.mkdir(exist_ok=True)
    (user_claude_dir / "CLAUDE.md").write_text("global user instructions")

    # Use a different dir as cwd so there's no overlap
    cwd = tmp_path / "project"
    cwd.mkdir()

    result = load_claude_md_hierarchy(str(cwd))
    assert any("global user instructions" in content for _, content in result)
    assert any("user" in label.lower() for label, _ in result)


def test_no_claude_md_returns_empty(tmp_path: Path):
    """No CLAUDE.md files at all returns empty list."""
    cwd = tmp_path / "emptyproject"
    cwd.mkdir()

    result = load_claude_md_hierarchy(str(cwd))
    assert result == []


def test_system_prompt_includes_claude_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """build_system_prompt includes content from all hierarchy levels."""
    fake_home = tmp_path / "_fakehome"
    user_claude = fake_home / ".claude"
    user_claude.mkdir(exist_ok=True)
    (user_claude / "CLAUDE.md").write_text("global rule A")

    cwd = tmp_path / "proj"
    cwd.mkdir()
    (cwd / "CLAUDE.md").write_text("project rule B")

    prompt = build_system_prompt(str(cwd))
    assert "global rule A" in prompt
    assert "project rule B" in prompt


def test_empty_claude_md_skipped(tmp_path: Path):
    """Empty CLAUDE.md files are skipped."""
    (tmp_path / "CLAUDE.md").write_text("")
    dot_claude = tmp_path / ".claude"
    dot_claude.mkdir()
    (dot_claude / "CLAUDE.md").write_text("  \n  ")
    result = load_claude_md_hierarchy(str(tmp_path))
    assert len(result) == 0


def test_hierarchy_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Results are ordered: user global, project .claude, project root."""
    fake_home = tmp_path / "_fakehome"
    user_claude = fake_home / ".claude"
    user_claude.mkdir(exist_ok=True)
    (user_claude / "CLAUDE.md").write_text("level-user")

    cwd = tmp_path / "proj"
    cwd.mkdir()
    dot_claude = cwd / ".claude"
    dot_claude.mkdir()
    (dot_claude / "CLAUDE.md").write_text("level-project-dotclaude")
    (cwd / "CLAUDE.md").write_text("level-project-root")

    result = load_claude_md_hierarchy(str(cwd))
    labels = [label for label, _ in result]
    assert len(result) == 3
    # user global comes first
    assert "user" in labels[0].lower()
    # project root comes last
    assert "root" in labels[2].lower() or "project" in labels[2].lower()
