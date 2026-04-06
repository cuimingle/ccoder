"""Build system and user context for API calls."""
from __future__ import annotations
import datetime
import os
import subprocess
from pathlib import Path


SYSTEM_PROMPT_BASE = """You are Claude Code, an AI coding assistant.

You help with software engineering tasks: writing code, debugging, refactoring, explaining code, and more.

Current date: {date}
Working directory: {cwd}
{claude_md_section}
{git_section}"""


def load_claude_md_hierarchy(cwd: str) -> list[tuple[str, str]]:
    """Load CLAUDE.md from multiple levels, deduplicating by resolved path.

    Levels (in order):
    1. User global: ~/.claude/CLAUDE.md
    2. Project .claude dir: <cwd>/.claude/CLAUDE.md
    3. Project root: <cwd>/CLAUDE.md

    Returns list of (source_label, content) tuples.
    Skips missing or empty/whitespace-only files.
    """
    candidates: list[tuple[str, Path]] = []

    # 1. User global
    home = os.environ.get("HOME", str(Path.home()))
    user_global = Path(home) / ".claude" / "CLAUDE.md"
    candidates.append(("User global (~/.claude/CLAUDE.md)", user_global))

    # 2. Project .claude dir
    project_dot_claude = Path(cwd) / ".claude" / "CLAUDE.md"
    candidates.append(("Project .claude dir", project_dot_claude))

    # 3. Project root
    project_root = Path(cwd) / "CLAUDE.md"
    candidates.append(("Project root", project_root))

    seen_paths: set[Path] = set()
    result: list[tuple[str, str]] = []

    for label, path in candidates:
        if not path.exists():
            continue
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not content.strip():
            continue
        result.append((label, content))

    return result


def load_claude_md(cwd: str) -> str:
    """Load CLAUDE.md from all hierarchy levels and combine with section headers."""
    entries = load_claude_md_hierarchy(cwd)
    if not entries:
        return ""
    parts: list[str] = []
    for label, content in entries:
        parts.append(f"### {label}\n{content}")
    return "\n\n".join(parts)


def get_git_status(cwd: str) -> str:
    """Get a brief git status summary."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"Git status:\n{result.stdout.strip()}"
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def build_system_prompt(cwd: str) -> str:
    """Build the system prompt for a new conversation turn."""
    date = datetime.date.today().isoformat()
    claude_md = load_claude_md(cwd)
    git_status = get_git_status(cwd)

    claude_md_section = (
        f"\n## Project Instructions (CLAUDE.md)\n{claude_md}\n" if claude_md else ""
    )
    git_section = f"\n{git_status}" if git_status else ""

    return SYSTEM_PROMPT_BASE.format(
        date=date,
        cwd=cwd,
        claude_md_section=claude_md_section,
        git_section=git_section,
    ).strip()
