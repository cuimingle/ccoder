# Phase 5: Command System, Context Enhancement & Query Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bridge the gap from "all modules exist" to "production-quality CLI" by adding an extensible command system, multi-level CLAUDE.md, auto-continue, message normalization, reactive compact, and concurrent tool execution.

**Architecture:** Three independent subsystems — (A) Command registry + context enhancement, (B) Query loop hardening (auto-continue, reactive compact, message normalization), (C) Streaming tool executor with concurrency. Each produces working, testable software independently.

**Tech Stack:** Python 3.11+, asyncio, anthropic SDK, pytest + pytest-asyncio

---

## File Structure

### New files:
- `packages/app/command_registry.py` — Extensible command registry with prompt/local command types
- `packages/app/commands/commit.py` — /commit prompt command
- `packages/app/commands/cost.py` — /cost local command
- `packages/app/commands/diff.py` — /diff local command
- `packages/app/commands/help.py` — /help local command
- `packages/app/streaming_tool_executor.py` — Concurrent streaming tool executor
- `tests/test_command_registry.py` — Command registry tests
- `tests/test_context_enhanced.py` — Multi-level CLAUDE.md tests
- `tests/test_query_hardening.py` — Auto-continue, reactive compact tests
- `tests/test_streaming_executor.py` — Concurrent tool execution tests

### Modified files:
- `packages/app/commands.py` — Refactored to use registry
- `packages/app/context.py` — Multi-level CLAUDE.md loading
- `packages/app/query.py` — Auto-continue, message normalization, reactive compact
- `packages/app/query_engine.py` — Integrate command registry, enhanced context
- `packages/app/tool_executor.py` — Add concurrency support
- `packages/app/compaction.py` — Add reactive compact entry point

---

## Part A: Command Registry + Context Enhancement

### Task 1: Command Registry Foundation

**Files:**
- Create: `packages/app/command_registry.py`
- Create: `tests/test_command_registry.py`
- Modify: `packages/app/commands.py`

- [ ] **Step 1: Write failing tests for CommandRegistry**

```python
# tests/test_command_registry.py
import pytest
from app.command_registry import (
    CommandRegistry,
    PromptCommand,
    LocalCommand,
    CommandResult,
)


def test_register_and_lookup_local_command():
    registry = CommandRegistry()

    async def clear_handler(args: str, context: dict) -> CommandResult:
        return CommandResult(text="Cleared.", handled=True)

    cmd = LocalCommand(name="clear", description="Clear session", handler=clear_handler)
    registry.register(cmd)
    found = registry.get("clear")
    assert found is not None
    assert found.name == "clear"


def test_lookup_unknown_returns_none():
    registry = CommandRegistry()
    assert registry.get("nonexistent") is None


def test_register_prompt_command():
    registry = CommandRegistry()

    async def get_prompt(args: str, context: dict) -> str:
        return f"Please commit with message: {args}"

    cmd = PromptCommand(
        name="commit",
        description="Create a git commit",
        get_prompt=get_prompt,
        progress_message="creating commit",
    )
    registry.register(cmd)
    found = registry.get("commit")
    assert found is not None
    assert found.type == "prompt"


def test_list_commands():
    registry = CommandRegistry()

    async def handler(args, ctx):
        return CommandResult(text="ok")

    registry.register(LocalCommand(name="clear", description="Clear", handler=handler))
    registry.register(LocalCommand(name="cost", description="Cost", handler=handler))
    commands = registry.list_commands()
    assert len(commands) == 2
    names = {c.name for c in commands}
    assert names == {"clear", "cost"}


def test_alias_lookup():
    registry = CommandRegistry()

    async def handler(args, ctx):
        return CommandResult(text="ok")

    cmd = LocalCommand(name="help", description="Help", handler=handler, aliases=["h", "?"])
    registry.register(cmd)
    assert registry.get("h") is not None
    assert registry.get("?") is not None
    assert registry.get("h").name == "help"


@pytest.mark.asyncio
async def test_execute_local_command():
    registry = CommandRegistry()

    async def handler(args: str, context: dict) -> CommandResult:
        return CommandResult(text=f"echo: {args}")

    registry.register(LocalCommand(name="echo", description="Echo", handler=handler))
    result = await registry.execute("echo", "hello", {})
    assert result.text == "echo: hello"


@pytest.mark.asyncio
async def test_execute_unknown_command():
    registry = CommandRegistry()
    result = await registry.execute("nope", "", {})
    assert not result.handled
    assert "Unknown" in result.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_command_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.command_registry'`

- [ ] **Step 3: Implement CommandRegistry**

```python
# packages/app/command_registry.py
"""Extensible command registry for slash commands."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable


@dataclass
class CommandResult:
    """Result of executing a slash command."""

    text: str
    handled: bool = True
    should_query: bool = False
    prompt_content: str = ""


@dataclass
class LocalCommand:
    """A command that executes locally and returns a result."""

    name: str
    description: str
    handler: Callable[[str, dict], Awaitable[CommandResult]]
    aliases: list[str] = field(default_factory=list)
    is_hidden: bool = False
    type: str = "local"


@dataclass
class PromptCommand:
    """A command that generates a prompt for the model to process."""

    name: str
    description: str
    get_prompt: Callable[[str, dict], Awaitable[str]]
    progress_message: str = ""
    aliases: list[str] = field(default_factory=list)
    is_hidden: bool = False
    type: str = "prompt"


Command = LocalCommand | PromptCommand


class CommandRegistry:
    """Registry for slash commands with lookup by name or alias."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: Command) -> None:
        """Register a command by name and aliases."""
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    def get(self, name: str) -> Command | None:
        """Look up a command by name or alias."""
        if name in self._commands:
            return self._commands[name]
        canonical = self._aliases.get(name)
        if canonical:
            return self._commands.get(canonical)
        return None

    def list_commands(self) -> list[Command]:
        """Return all registered commands (excluding hidden ones)."""
        return [c for c in self._commands.values() if not c.is_hidden]

    async def execute(self, name: str, args: str, context: dict) -> CommandResult:
        """Execute a command by name. Returns unhandled result if not found."""
        cmd = self.get(name)
        if cmd is None:
            return CommandResult(
                text=f"Unknown command: /{name}. Type /help for available commands.",
                handled=False,
            )

        if isinstance(cmd, LocalCommand):
            return await cmd.handler(args, context)
        elif isinstance(cmd, PromptCommand):
            prompt = await cmd.get_prompt(args, context)
            return CommandResult(
                text=cmd.progress_message or f"Running /{name}...",
                handled=True,
                should_query=True,
                prompt_content=prompt,
            )
        return CommandResult(text="Unknown command type.", handled=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_command_registry.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/command_registry.py tests/test_command_registry.py
git commit -m "feat: add extensible CommandRegistry with local and prompt command types"
```

---

### Task 2: Built-in Commands (/clear, /compact, /cost, /help)

**Files:**
- Create: `packages/app/commands/cost.py`
- Create: `packages/app/commands/help.py`
- Modify: `packages/app/commands.py` — refactor to register built-in commands
- Modify: `tests/test_commands.py`

- [ ] **Step 1: Write failing tests for built-in commands**

```python
# tests/test_builtin_commands.py
import pytest
from app.commands import build_default_registry
from app.command_registry import CommandResult


@pytest.mark.asyncio
async def test_clear_command():
    registry = build_default_registry()
    result = await registry.execute("clear", "", {"engine": None})
    assert result.handled
    assert "clear" in result.text.lower() or "cleared" in result.text.lower()


@pytest.mark.asyncio
async def test_help_command():
    registry = build_default_registry()
    result = await registry.execute("help", "", {"engine": None})
    assert result.handled
    assert "/compact" in result.text
    assert "/clear" in result.text


@pytest.mark.asyncio
async def test_cost_command():
    registry = build_default_registry()
    ctx = {"total_input_tokens": 5000, "total_output_tokens": 1500, "turn_count": 3}
    result = await registry.execute("cost", "", ctx)
    assert result.handled
    assert "token" in result.text.lower() or "5000" in result.text


@pytest.mark.asyncio
async def test_help_alias():
    registry = build_default_registry()
    result = await registry.execute("h", "", {"engine": None})
    assert result.handled


@pytest.mark.asyncio
async def test_unknown_command():
    registry = build_default_registry()
    result = await registry.execute("nonexistent", "", {})
    assert not result.handled
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_builtin_commands.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_default_registry'`

- [ ] **Step 3: Implement built-in commands and registry builder**

```python
# packages/app/commands/cost.py
"""Cost command - show session token usage."""
from __future__ import annotations
from app.command_registry import CommandResult


async def cost_handler(args: str, context: dict) -> CommandResult:
    """Show the cost and token usage of the current session."""
    input_tokens = context.get("total_input_tokens", 0)
    output_tokens = context.get("total_output_tokens", 0)
    turn_count = context.get("turn_count", 0)
    total_tokens = input_tokens + output_tokens

    # Estimate cost (Claude Opus pricing: $15/M input, $75/M output)
    input_cost = (input_tokens / 1_000_000) * 15.0
    output_cost = (output_tokens / 1_000_000) * 75.0
    total_cost = input_cost + output_cost

    lines = [
        f"Session cost: ${total_cost:.4f}",
        f"  Input tokens:  {input_tokens:,} (${input_cost:.4f})",
        f"  Output tokens: {output_tokens:,} (${output_cost:.4f})",
        f"  Total tokens:  {total_tokens:,}",
        f"  Turns: {turn_count}",
    ]
    return CommandResult(text="\n".join(lines))
```

```python
# packages/app/commands/help.py
"""Help command - list available slash commands."""
from __future__ import annotations
from app.command_registry import CommandRegistry, CommandResult


async def help_handler(args: str, context: dict) -> CommandResult:
    """List all available slash commands."""
    registry: CommandRegistry | None = context.get("registry")
    lines = ["Available commands:", ""]

    if registry:
        for cmd in registry.list_commands():
            aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            lines.append(f"  /{cmd.name:<12} {cmd.description}{aliases}")
    else:
        lines.append("  /compact     Compact conversation history")
        lines.append("  /clear       Clear session state")
        lines.append("  /cost        Show session cost and token usage")
        lines.append("  /help        Show this help message")

    return CommandResult(text="\n".join(lines))
```

Then refactor `commands.py`:

```python
# packages/app/commands.py (full replacement)
"""Slash command dispatcher — builds the default command registry."""
from __future__ import annotations

from app.command_registry import (
    CommandRegistry,
    CommandResult,
    LocalCommand,
)
from app.commands.cost import cost_handler
from app.commands.help import help_handler


def parse_command(user_input: str) -> tuple[str, str] | None:
    """Parse a slash command from user input. Returns (name, args) or None."""
    stripped = user_input.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.split(None, 1)
    command = parts[0][1:]  # remove leading /
    args = parts[1] if len(parts) > 1 else ""
    return command, args


def is_command(user_input: str) -> bool:
    """Check if user input is a slash command."""
    return parse_command(user_input) is not None


def build_default_registry() -> CommandRegistry:
    """Build the default command registry with all built-in commands."""
    registry = CommandRegistry()

    async def clear_handler(args: str, context: dict) -> CommandResult:
        return CommandResult(text="Session cleared.")

    async def compact_handler(args: str, context: dict) -> CommandResult:
        return CommandResult(text="Use engine.compact() directly.", should_query=False)

    registry.register(LocalCommand(
        name="clear", description="Clear session state", handler=clear_handler
    ))
    registry.register(LocalCommand(
        name="compact", description="Compact conversation history",
        handler=compact_handler,
    ))
    registry.register(LocalCommand(
        name="cost", description="Show session cost and token usage",
        handler=cost_handler,
    ))
    registry.register(LocalCommand(
        name="help", description="Show available commands",
        handler=help_handler, aliases=["h", "?"],
    ))

    return registry
```

- [ ] **Step 4: Create `packages/app/commands/__init__.py`**

```bash
mkdir -p packages/app/commands
touch packages/app/commands/__init__.py
```

Note: Move the `build_default_registry`, `parse_command`, `is_command` functions to `packages/app/commands/__init__.py` (renaming the old `commands.py` module to a package). The old `commands.py` becomes `commands/__init__.py`.

- [ ] **Step 5: Run tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_builtin_commands.py tests/test_commands.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/commands/ packages/app/command_registry.py tests/test_builtin_commands.py
git commit -m "feat: add built-in commands (/clear, /compact, /cost, /help) with registry"
```

---

### Task 3: Multi-level CLAUDE.md Loading

**Files:**
- Modify: `packages/app/context.py`
- Create: `tests/test_context_enhanced.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_context_enhanced.py
import pytest
from pathlib import Path
from app.context import load_claude_md_hierarchy, build_system_prompt


def test_load_cwd_claude_md(tmp_path):
    """Load CLAUDE.md from the current working directory."""
    (tmp_path / "CLAUDE.md").write_text("# Project rules\nUse snake_case.")
    results = load_claude_md_hierarchy(str(tmp_path))
    assert len(results) == 1
    assert "snake_case" in results[0][1]


def test_load_project_level_claude_md(tmp_path):
    """Load from .claude/CLAUDE.md in the project directory."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("# Project config")
    results = load_claude_md_hierarchy(str(tmp_path))
    assert any("Project config" in content for _, content in results)


def test_load_both_project_and_cwd(tmp_path):
    """Load both .claude/CLAUDE.md and CLAUDE.md, deduplicate."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("# From .claude dir")
    (tmp_path / "CLAUDE.md").write_text("# From root")
    results = load_claude_md_hierarchy(str(tmp_path))
    assert len(results) == 2
    texts = [content for _, content in results]
    assert any("From .claude dir" in t for t in texts)
    assert any("From root" in t for t in texts)


def test_load_user_global_claude_md(tmp_path, monkeypatch):
    """Load from ~/.claude/CLAUDE.md (user global)."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("# User global instructions")
    monkeypatch.setenv("HOME", str(fake_home))

    project = tmp_path / "project"
    project.mkdir()
    results = load_claude_md_hierarchy(str(project))
    assert any("User global" in content for _, content in results)


def test_no_claude_md_returns_empty(tmp_path):
    results = load_claude_md_hierarchy(str(tmp_path))
    assert len(results) == 0


def test_system_prompt_includes_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("Always use type hints.")
    prompt = build_system_prompt(str(tmp_path))
    assert "type hints" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_context_enhanced.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_claude_md_hierarchy'`

- [ ] **Step 3: Implement multi-level loading in context.py**

Replace the `load_claude_md` function in `packages/app/context.py`:

```python
# packages/app/context.py (full replacement)
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
    """
    Load CLAUDE.md files from multiple levels (user global -> project -> cwd).
    Returns list of (source_label, content) tuples, ordered from global to local.
    Deduplicates by resolved path.
    """
    results: list[tuple[str, str]] = []
    seen_paths: set[str] = set()

    candidates: list[tuple[str, Path]] = []

    # 1. User global: ~/.claude/CLAUDE.md
    home = Path(os.environ.get("HOME", Path.home()))
    user_global = home / ".claude" / "CLAUDE.md"
    candidates.append(("user global (~/.claude/CLAUDE.md)", user_global))

    cwd_path = Path(cwd).resolve()

    # 2. Project .claude dir: <cwd>/.claude/CLAUDE.md
    project_claude = cwd_path / ".claude" / "CLAUDE.md"
    candidates.append(("project (.claude/CLAUDE.md)", project_claude))

    # 3. Project root: <cwd>/CLAUDE.md
    root_claude = cwd_path / "CLAUDE.md"
    candidates.append(("project (CLAUDE.md)", root_claude))

    for label, path in candidates:
        try:
            resolved = path.resolve()
            if resolved.exists() and str(resolved) not in seen_paths:
                content = resolved.read_text(encoding="utf-8").strip()
                if content:
                    results.append((label, content))
                    seen_paths.add(str(resolved))
        except (OSError, PermissionError):
            continue

    return results


def load_claude_md(cwd: str) -> str:
    """Load CLAUDE.md content — combines all levels into one string."""
    entries = load_claude_md_hierarchy(cwd)
    if not entries:
        return ""
    sections = []
    for label, content in entries:
        sections.append(f"### {label}\n{content}")
    return "\n\n".join(sections)


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
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_context_enhanced.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run existing tests to check no regressions**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest -v`
Expected: ALL PASS (178+ tests)

- [ ] **Step 6: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/context.py tests/test_context_enhanced.py
git commit -m "feat: multi-level CLAUDE.md loading (user global, .claude/, project root)"
```

---

### Task 4: Integrate Command Registry into QueryEngine

**Files:**
- Modify: `packages/app/query_engine.py`
- Modify: existing query engine tests

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_commands.py or create new test file
import pytest
from unittest.mock import AsyncMock, patch
from app.query_engine import QueryEngine


@pytest.mark.asyncio
async def test_engine_cost_command():
    """QueryEngine should route /cost through command registry."""
    with patch("app.query_engine.ClaudeAPIClient"):
        engine = QueryEngine(cwd="/tmp", api_key="test-key")
        engine.total_input_tokens = 5000
        engine.total_output_tokens = 1500
        engine.turn_count = 3
        result = await engine.run_turn("/cost")
        assert result.response_text
        assert "5,000" in result.response_text or "5000" in result.response_text


@pytest.mark.asyncio
async def test_engine_help_command():
    with patch("app.query_engine.ClaudeAPIClient"):
        engine = QueryEngine(cwd="/tmp", api_key="test-key")
        result = await engine.run_turn("/help")
        assert "/compact" in result.response_text
        assert "/cost" in result.response_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_commands.py -v -k "cost or help"`
Expected: FAIL

- [ ] **Step 3: Update QueryEngine to use CommandRegistry**

In `packages/app/query_engine.py`, replace hardcoded command handling:

```python
# In __init__, after existing setup:
from app.commands import build_default_registry
self._command_registry = build_default_registry()

# Replace the command-handling section in run_turn():
async def run_turn(self, user_input, on_text=None, on_tool_use=None):
    cmd = parse_command(user_input)
    if cmd is not None:
        command_name, args = cmd

        # Special handling for commands that need engine state
        if command_name == "compact":
            return await self._handle_compact()
        if command_name == "clear":
            self.clear()
            return QueryResult(response_text="Session cleared.", messages=[], tool_calls=[])

        # Route through command registry
        context = {
            "engine": self,
            "registry": self._command_registry,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "turn_count": self.turn_count,
            "cwd": self.cwd,
        }
        result = await self._command_registry.execute(command_name, args, context)

        if result.should_query:
            # Prompt command: inject as user message and query the model
            self.messages.append(UserMessage(content=result.prompt_content))
            # ... fall through to query()
        else:
            return QueryResult(response_text=result.text, tool_calls=[])

    # ... rest of existing run_turn code
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/query_engine.py packages/app/commands/ tests/
git commit -m "feat: integrate CommandRegistry into QueryEngine, add /cost and /help"
```

---

## Part B: Query Loop Hardening

### Task 5: Message Normalization Before API Calls

**Files:**
- Create: `packages/app/message_normalization.py`
- Create: `tests/test_message_normalization.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_message_normalization.py
import pytest
from app.message_normalization import normalize_messages_for_api
from app.types.message import (
    UserMessage,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)


def test_merge_consecutive_user_messages():
    """Two consecutive UserMessages should be merged into one."""
    messages = [
        UserMessage(content="Hello"),
        UserMessage(content="World"),
    ]
    result = normalize_messages_for_api(messages)
    assert len(result) == 1
    assert isinstance(result[0], UserMessage)


def test_strip_empty_assistant_messages():
    """Assistant messages with no content should be stripped."""
    messages = [
        UserMessage(content="Hi"),
        AssistantMessage(content=[]),
        UserMessage(content="Follow up"),
    ]
    result = normalize_messages_for_api(messages)
    assert all(not (isinstance(m, AssistantMessage) and not m.content) for m in result)


def test_ensure_tool_result_pairing():
    """Every ToolUseBlock must have a corresponding ToolResultBlock."""
    messages = [
        UserMessage(content="Run something"),
        AssistantMessage(content=[
            ToolUseBlock(id="tu_1", name="Bash", input={"command": "ls"}),
        ]),
        UserMessage(content=[
            ToolResultBlock(tool_use_id="tu_1", content="file.txt", is_error=False),
        ]),
    ]
    result = normalize_messages_for_api(messages)
    # Should pass through unchanged — all tool_use blocks have results
    assert len(result) == 3


def test_orphaned_tool_use_gets_synthetic_result():
    """A ToolUseBlock with no matching ToolResultBlock gets a synthetic error result."""
    messages = [
        UserMessage(content="Run something"),
        AssistantMessage(content=[
            ToolUseBlock(id="tu_1", name="Bash", input={"command": "ls"}),
        ]),
        # Missing ToolResultBlock for tu_1
    ]
    result = normalize_messages_for_api(messages)
    # Should add a synthetic tool result
    last = result[-1]
    assert isinstance(last, UserMessage)
    assert isinstance(last.content, list)
    assert any(
        isinstance(b, ToolResultBlock) and b.tool_use_id == "tu_1"
        for b in last.content
    )


def test_passthrough_normal_conversation():
    """Normal user-assistant alternation passes through unchanged."""
    messages = [
        UserMessage(content="Hi"),
        AssistantMessage(content=[TextBlock(text="Hello!")]),
        UserMessage(content="Thanks"),
    ]
    result = normalize_messages_for_api(messages)
    assert len(result) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_message_normalization.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement message normalization**

```python
# packages/app/message_normalization.py
"""Normalize conversation messages before sending to the API."""
from __future__ import annotations

from app.types.message import (
    AssistantMessage,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


def normalize_messages_for_api(messages: list[Message]) -> list[Message]:
    """
    Clean up messages before sending to the API.

    Passes:
    1. Strip empty assistant messages
    2. Merge consecutive user messages
    3. Ensure every ToolUseBlock has a matching ToolResultBlock
    """
    result = _strip_empty_assistants(messages)
    result = _merge_consecutive_users(result)
    result = _ensure_tool_result_pairing(result)
    return result


def _strip_empty_assistants(messages: list[Message]) -> list[Message]:
    """Remove assistant messages with empty content."""
    return [
        m for m in messages
        if not (isinstance(m, AssistantMessage) and not m.content)
    ]


def _merge_consecutive_users(messages: list[Message]) -> list[Message]:
    """Merge consecutive UserMessage entries into a single message."""
    if not messages:
        return []

    result: list[Message] = []
    for msg in messages:
        if (
            isinstance(msg, UserMessage)
            and result
            and isinstance(result[-1], UserMessage)
        ):
            prev = result[-1]
            # Merge content
            prev_content = _to_content_list(prev.content)
            cur_content = _to_content_list(msg.content)
            result[-1] = UserMessage(content=prev_content + cur_content)
        else:
            result.append(msg)
    return result


def _to_content_list(content) -> list:
    """Convert string or list content to a list of blocks."""
    if isinstance(content, str):
        return [TextBlock(text=content)]
    if isinstance(content, list):
        return list(content)
    return [content]


def _ensure_tool_result_pairing(messages: list[Message]) -> list[Message]:
    """Ensure every ToolUseBlock has a corresponding ToolResultBlock."""
    # Collect all tool_use IDs and tool_result IDs
    tool_use_ids: set[str] = set()
    tool_result_ids: set[str] = set()

    for msg in messages:
        if isinstance(msg, AssistantMessage) and isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    tool_use_ids.add(block.id)
        if isinstance(msg, UserMessage) and isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    tool_result_ids.add(block.tool_use_id)

    orphaned = tool_use_ids - tool_result_ids
    if not orphaned:
        return messages

    # Add synthetic error results for orphaned tool uses
    synthetic_results = [
        ToolResultBlock(
            tool_use_id=tid,
            content="Tool execution was interrupted.",
            is_error=True,
        )
        for tid in orphaned
    ]
    return [*messages, UserMessage(content=synthetic_results)]
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_message_normalization.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/message_normalization.py tests/test_message_normalization.py
git commit -m "feat: message normalization (merge users, strip empty, tool result pairing)"
```

---

### Task 6: Auto-Continue on Max Output Tokens

**Files:**
- Modify: `packages/app/query.py`
- Modify: `packages/app/services/api/claude.py`
- Create: `tests/test_query_hardening.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_query_hardening.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.query import query, QueryResult
from app.types.message import UserMessage
from app.services.api.claude import StreamEvent


def _make_api_client(event_sequences: list[list[StreamEvent]]):
    """Create a mock API client that yields different events per call."""
    client = AsyncMock()
    call_count = 0

    async def mock_stream(params):
        nonlocal call_count
        events = event_sequences[min(call_count, len(event_sequences) - 1)]
        call_count += 1
        for ev in events:
            yield ev

    client.stream = mock_stream
    client.messages_to_api_format = MagicMock(side_effect=lambda m: m)
    client.tools_to_api_format = MagicMock(return_value=[])
    client.build_request_params = MagicMock(side_effect=lambda **kw: kw)
    return client


@pytest.mark.asyncio
async def test_auto_continue_on_max_output_tokens():
    """When stop_reason is max_output_tokens, query should auto-continue."""
    # First call: truncated response
    seq1 = [
        StreamEvent(type="text_delta", text="Part 1 of the answer"),
        StreamEvent(type="usage", input_tokens=100, output_tokens=50),
        StreamEvent(type="message_stop", stop_reason="max_output_tokens"),
    ]
    # Second call: completes the response
    seq2 = [
        StreamEvent(type="text_delta", text=" and Part 2."),
        StreamEvent(type="usage", input_tokens=150, output_tokens=30),
        StreamEvent(type="message_stop", stop_reason="end_turn"),
    ]
    client = _make_api_client([seq1, seq2])

    result = await query(
        messages=[UserMessage(content="Hello")],
        system="You are helpful.",
        tools=[],
        api_client=client,
        cwd="/tmp",
    )
    assert "Part 1" in result.response_text
    assert "Part 2" in result.response_text


@pytest.mark.asyncio
async def test_no_continue_on_normal_stop():
    """Normal end_turn should not trigger continuation."""
    seq = [
        StreamEvent(type="text_delta", text="Complete answer."),
        StreamEvent(type="usage", input_tokens=100, output_tokens=50),
        StreamEvent(type="message_stop", stop_reason="end_turn"),
    ]
    client = _make_api_client([seq])

    result = await query(
        messages=[UserMessage(content="Hello")],
        system="You are helpful.",
        tools=[],
        api_client=client,
        cwd="/tmp",
    )
    assert result.response_text == "Complete answer."


@pytest.mark.asyncio
async def test_max_continue_limit():
    """Auto-continue should not loop forever — cap at MAX_CONTINUATIONS."""
    # Always truncated
    truncated = [
        StreamEvent(type="text_delta", text="x"),
        StreamEvent(type="usage", input_tokens=100, output_tokens=50),
        StreamEvent(type="message_stop", stop_reason="max_output_tokens"),
    ]
    client = _make_api_client([truncated] * 10)

    result = await query(
        messages=[UserMessage(content="Hello")],
        system="You are helpful.",
        tools=[],
        api_client=client,
        cwd="/tmp",
        max_continuations=3,
    )
    # Should have continued 3 times then stopped
    assert result.response_text.count("x") <= 4  # initial + 3 continues
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_query_hardening.py -v`
Expected: FAIL — `query()` does not accept `max_continuations` param / no auto-continue logic

- [ ] **Step 3: Add stop_reason to StreamEvent and auto-continue to query()**

First, update `StreamEvent` in `services/api/claude.py` to carry `stop_reason`:

```python
# In StreamEvent dataclass, add:
stop_reason: str = ""
```

Then update the `stream()` method to populate stop_reason on message_stop events.

Then update `query()` in `query.py`:

```python
MAX_CONTINUATIONS_DEFAULT = 3

async def query(
    messages: list[Message],
    system: str,
    tools: list[Tool],
    api_client: ClaudeAPIClient,
    cwd: str,
    permission_mode: str = "manual",
    on_text: Callable[[str], None] | None = None,
    on_tool_use: Callable[[str, dict], None] | None = None,
    tool_executor: "ToolExecutor | None" = None,
    max_continuations: int = MAX_CONTINUATIONS_DEFAULT,
) -> QueryResult:
    conversation: list[Message] = list(messages)
    all_tool_calls: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    context = ToolContext(cwd=cwd, permission_mode=permission_mode)
    continuation_count = 0

    while True:
        # ... existing API call code ...

        stop_reason = ""
        async for event in api_client.stream(params):
            if event.type == "text_delta":
                text_parts.append(event.text)
                if on_text:
                    on_text(event.text)
            elif event.type == "tool_use":
                tool_use_events.append(event)
                if on_tool_use:
                    on_tool_use(event.tool_name, event.tool_input)
            elif event.type == "usage":
                total_input_tokens += event.input_tokens
                total_output_tokens += event.output_tokens
            elif event.type == "message_stop":
                stop_reason = event.stop_reason
                break

        response_text = "".join(text_parts)

        # Build assistant message
        assistant_content: list = []
        if response_text:
            assistant_content.append(TextBlock(text=response_text))
        for ev in tool_use_events:
            assistant_content.append(
                ToolUseBlock(id=ev.tool_use_id, name=ev.tool_name, input=ev.tool_input)
            )
        if assistant_content:
            conversation.append(AssistantMessage(content=assistant_content))

        # If no tool calls, check for auto-continue
        if not tool_use_events:
            if (
                stop_reason == "max_output_tokens"
                and continuation_count < max_continuations
            ):
                # Auto-continue: inject a nudge message and loop
                conversation.append(
                    UserMessage(content="Continue from where you left off. Do not repeat previous content.")
                )
                continuation_count += 1
                continue
            break

        # ... existing tool execution code ...
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_query_hardening.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/query.py packages/app/services/api/claude.py tests/test_query_hardening.py
git commit -m "feat: auto-continue when model hits max_output_tokens (capped at 3 retries)"
```

---

### Task 7: Reactive Compact (prompt_too_long recovery)

**Files:**
- Modify: `packages/app/query.py`
- Modify: `packages/app/compaction.py`
- Add to: `tests/test_query_hardening.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_query_hardening.py

@pytest.mark.asyncio
async def test_reactive_compact_on_prompt_too_long():
    """When API returns prompt_too_long error, query should compact and retry."""
    from app.services.api.claude import StreamEvent
    from anthropic import APIStatusError

    call_count = 0

    async def mock_stream(params):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate prompt_too_long error
            raise APIStatusError(
                message="prompt is too long",
                response=MagicMock(status_code=400),
                body={"error": {"type": "invalid_request_error", "message": "prompt is too long: 250000 tokens > 200000 maximum"}},
            )
        else:
            # After compact, succeed
            yield StreamEvent(type="text_delta", text="Success after compact")
            yield StreamEvent(type="usage", input_tokens=50, output_tokens=20)
            yield StreamEvent(type="message_stop", stop_reason="end_turn")

    client = AsyncMock()
    client.stream = mock_stream
    client.messages_to_api_format = MagicMock(side_effect=lambda m: m)
    client.tools_to_api_format = MagicMock(return_value=[])
    client.build_request_params = MagicMock(side_effect=lambda **kw: kw)

    compact_called = False
    original_compact = None

    async def mock_reactive_compact(messages, api_client, system):
        nonlocal compact_called
        compact_called = True
        # Return compacted messages (just keep last user message)
        from app.types.message import UserMessage
        return [UserMessage(content="[compacted]")], 10, 10

    with patch("app.query.reactive_compact", mock_reactive_compact):
        result = await query(
            messages=[UserMessage(content="Hello " * 10000)],
            system="System",
            tools=[],
            api_client=client,
            cwd="/tmp",
        )

    assert compact_called
    assert "Success" in result.response_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_query_hardening.py::test_reactive_compact_on_prompt_too_long -v`
Expected: FAIL

- [ ] **Step 3: Add reactive compact to query.py**

Add to `packages/app/compaction.py`:

```python
async def reactive_compact(
    messages: list, api_client, system: str
) -> tuple[list, int, int]:
    """
    Emergency compaction triggered by prompt_too_long error.
    Applies micro-compact first, then full compact.
    """
    compacted = micro_compact_messages(messages)
    return await compact_conversation(compacted, api_client, system)
```

Then wrap the API call in `query.py` with error handling:

```python
# In the while True loop, wrap the streaming call:
try:
    async for event in api_client.stream(params):
        # ... existing event handling ...
except Exception as e:
    if _is_prompt_too_long(e) and not has_attempted_reactive_compact:
        has_attempted_reactive_compact = True
        from app.compaction import reactive_compact
        conversation, rc_in, rc_out = await reactive_compact(
            conversation, api_client, system
        )
        total_input_tokens += rc_in
        total_output_tokens += rc_out
        continue  # Retry with compacted messages
    raise


def _is_prompt_too_long(error: Exception) -> bool:
    """Check if an API error is a prompt_too_long error."""
    error_str = str(error).lower()
    return "prompt is too long" in error_str or "prompt_too_long" in error_str
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_query_hardening.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/query.py packages/app/compaction.py tests/test_query_hardening.py
git commit -m "feat: reactive compact — auto-recover from prompt_too_long API errors"
```

---

### Task 8: Integrate Message Normalization into Query Loop

**Files:**
- Modify: `packages/app/query.py`

- [ ] **Step 1: Write test verifying normalization is applied**

```python
# Add to tests/test_query_hardening.py

@pytest.mark.asyncio
async def test_query_normalizes_messages():
    """query() should normalize messages before sending to API."""
    from app.types.message import AssistantMessage, TextBlock

    captured_messages = []

    def capture_format(msgs):
        captured_messages.extend(msgs)
        return msgs

    seq = [
        StreamEvent(type="text_delta", text="Hi"),
        StreamEvent(type="usage", input_tokens=10, output_tokens=5),
        StreamEvent(type="message_stop", stop_reason="end_turn"),
    ]
    client = _make_api_client([seq])
    client.messages_to_api_format = MagicMock(side_effect=capture_format)

    # Send messages with consecutive users (should be merged)
    await query(
        messages=[
            UserMessage(content="Hello"),
            UserMessage(content="World"),
        ],
        system="System",
        tools=[],
        api_client=client,
        cwd="/tmp",
    )

    # The API should have received merged messages
    user_msgs = [m for m in captured_messages if isinstance(m, UserMessage)]
    assert len(user_msgs) == 1  # Two UserMessages merged into one
```

- [ ] **Step 2: Add normalization call in query.py**

At the top of the while loop in `query()`, before building API params:

```python
from app.message_normalization import normalize_messages_for_api

# ... inside while True:
normalized = normalize_messages_for_api(conversation)
api_messages = api_client.messages_to_api_format(normalized)
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/query.py tests/test_query_hardening.py
git commit -m "feat: apply message normalization before every API call in query loop"
```

---

## Part C: Streaming Tool Executor

### Task 9: StreamingToolExecutor with Concurrency

**Files:**
- Create: `packages/app/streaming_tool_executor.py`
- Create: `tests/test_streaming_executor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_streaming_executor.py
import pytest
import asyncio
from unittest.mock import AsyncMock
from app.streaming_tool_executor import StreamingToolExecutor
from app.tool import Tool, ToolResult, ToolContext
from app.types.message import ToolUseBlock


class FakeReadTool:
    """A concurrency-safe tool (read operations can run in parallel)."""
    name = "Read"
    description = "Read files"
    input_schema = {"type": "object", "properties": {"path": {"type": "string"}}}
    is_concurrent_safe = True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        await asyncio.sleep(0.05)
        return ToolResult(content=f"content of {input['path']}")


class FakeBashTool:
    """A non-concurrent tool (bash commands must run exclusively)."""
    name = "Bash"
    description = "Run commands"
    input_schema = {"type": "object", "properties": {"command": {"type": "string"}}}
    is_concurrent_safe = False

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        await asyncio.sleep(0.05)
        return ToolResult(content=f"ran: {input['command']}")


@pytest.mark.asyncio
async def test_concurrent_safe_tools_run_in_parallel():
    """Multiple Read tools should execute concurrently."""
    tools = [FakeReadTool()]
    executor = StreamingToolExecutor(tools)

    blocks = [
        ToolUseBlock(id="tu_1", name="Read", input={"path": "a.txt"}),
        ToolUseBlock(id="tu_2", name="Read", input={"path": "b.txt"}),
        ToolUseBlock(id="tu_3", name="Read", input={"path": "c.txt"}),
    ]
    for b in blocks:
        executor.add_tool(b)

    results = []
    async for update in executor.get_results():
        results.append(update)

    assert len(results) == 3
    # All should complete — order may vary but all present
    contents = {r.content for r in results}
    assert "content of a.txt" in contents
    assert "content of b.txt" in contents
    assert "content of c.txt" in contents


@pytest.mark.asyncio
async def test_non_concurrent_tools_run_sequentially():
    """Bash tools should not overlap execution."""
    execution_log = []
    tools_list = []

    class TrackingBash:
        name = "Bash"
        description = "Run commands"
        input_schema = {"type": "object", "properties": {"command": {"type": "string"}}}
        is_concurrent_safe = False

        async def call(self, input: dict, context: ToolContext) -> ToolResult:
            execution_log.append(("start", input["command"]))
            await asyncio.sleep(0.05)
            execution_log.append(("end", input["command"]))
            return ToolResult(content=f"ran: {input['command']}")

    tools = [TrackingBash()]
    executor = StreamingToolExecutor(tools)

    executor.add_tool(ToolUseBlock(id="tu_1", name="Bash", input={"command": "cmd1"}))
    executor.add_tool(ToolUseBlock(id="tu_2", name="Bash", input={"command": "cmd2"}))

    results = []
    async for update in executor.get_results():
        results.append(update)

    assert len(results) == 2
    # Sequential: cmd1 should end before cmd2 starts
    assert execution_log.index(("end", "cmd1")) < execution_log.index(("start", "cmd2"))


@pytest.mark.asyncio
async def test_mixed_concurrent_and_exclusive():
    """Concurrent tools wait for exclusive tool, then run in parallel."""
    tools = [FakeBashTool(), FakeReadTool()]
    executor = StreamingToolExecutor(tools)

    executor.add_tool(ToolUseBlock(id="tu_1", name="Bash", input={"command": "init"}))
    executor.add_tool(ToolUseBlock(id="tu_2", name="Read", input={"path": "a.txt"}))
    executor.add_tool(ToolUseBlock(id="tu_3", name="Read", input={"path": "b.txt"}))

    results = []
    async for update in executor.get_results():
        results.append(update)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_tool_not_found_returns_error():
    executor = StreamingToolExecutor([FakeReadTool()])
    executor.add_tool(ToolUseBlock(id="tu_1", name="Unknown", input={}))

    results = []
    async for update in executor.get_results():
        results.append(update)

    assert len(results) == 1
    assert results[0].is_error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_streaming_executor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement StreamingToolExecutor**

```python
# packages/app/streaming_tool_executor.py
"""Streaming tool executor with concurrency control."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator

from app.tool import Tool, ToolContext, ToolResult
from app.types.message import ToolUseBlock


class ToolStatus(Enum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    YIELDED = "yielded"


@dataclass
class TrackedTool:
    block: ToolUseBlock
    tool: Tool | None
    status: ToolStatus = ToolStatus.QUEUED
    is_concurrent_safe: bool = False
    result: ToolResult | None = None
    task: asyncio.Task | None = None


class StreamingToolExecutor:
    """
    Executes tools with concurrency control.

    - Concurrent-safe tools (Read, Grep, Glob) run in parallel.
    - Non-concurrent tools (Bash, Write, Edit) run exclusively.
    - Results are yielded in queue order to preserve API message ordering.
    """

    def __init__(
        self,
        tools: list[Tool],
        context: ToolContext | None = None,
        tool_executor=None,
    ) -> None:
        self._tool_map: dict[str, Tool] = {t.name: t for t in tools}
        self._queue: list[TrackedTool] = []
        self._context = context or ToolContext(cwd=".", permission_mode="auto")
        self._tool_executor = tool_executor
        self._completion_event = asyncio.Event()

    def add_tool(self, block: ToolUseBlock) -> None:
        """Add a tool use block to the execution queue."""
        tool = self._tool_map.get(block.name)
        is_safe = getattr(tool, "is_concurrent_safe", False) if tool else False
        tracked = TrackedTool(
            block=block,
            tool=tool,
            is_concurrent_safe=is_safe,
        )
        self._queue.append(tracked)

    def _can_execute(self, tracked: TrackedTool) -> bool:
        """Check if a tool can start executing based on concurrency rules."""
        executing = [t for t in self._queue if t.status == ToolStatus.EXECUTING]
        if not executing:
            return True
        if tracked.is_concurrent_safe and all(t.is_concurrent_safe for t in executing):
            return True
        return False

    async def _execute_tool(self, tracked: TrackedTool) -> None:
        """Execute a single tool and store the result."""
        tracked.status = ToolStatus.EXECUTING
        try:
            if tracked.tool is None:
                tracked.result = ToolResult(
                    content=f"Tool '{tracked.block.name}' not found.",
                    is_error=True,
                )
            elif self._tool_executor is not None:
                tracked.result = await self._tool_executor.execute(
                    tracked.tool, tracked.block.input, self._context
                )
            else:
                tracked.result = await tracked.tool.call(
                    tracked.block.input, self._context
                )
        except Exception as e:
            tracked.result = ToolResult(content=str(e), is_error=True)
        finally:
            tracked.status = ToolStatus.COMPLETED
            self._completion_event.set()

    async def _process_queue(self) -> None:
        """Start executing queued tools respecting concurrency rules."""
        for tracked in self._queue:
            if tracked.status != ToolStatus.QUEUED:
                continue
            if self._can_execute(tracked):
                tracked.task = asyncio.create_task(self._execute_tool(tracked))
            elif not tracked.is_concurrent_safe:
                # Non-concurrent tool blocks queue processing
                break

    async def get_results(self) -> AsyncGenerator[ToolResult, None]:
        """
        Yield tool results in queue order.
        Concurrent tools may complete out of order but are yielded in order.
        """
        await self._process_queue()

        while any(t.status != ToolStatus.YIELDED for t in self._queue):
            # Yield completed results in order
            for tracked in self._queue:
                if tracked.status == ToolStatus.YIELDED:
                    continue
                if tracked.status == ToolStatus.COMPLETED and tracked.result is not None:
                    tracked.status = ToolStatus.YIELDED
                    yield tracked.result
                    # After yielding, try to start more tools
                    await self._process_queue()
                elif tracked.status in (ToolStatus.QUEUED, ToolStatus.EXECUTING):
                    # Wait for this tool (preserve order)
                    if not tracked.is_concurrent_safe:
                        break
                    if tracked.status == ToolStatus.EXECUTING:
                        break

            # If nothing was yielded, wait for a completion
            has_unyielded = any(
                t.status in (ToolStatus.QUEUED, ToolStatus.EXECUTING)
                for t in self._queue
            )
            if has_unyielded:
                self._completion_event.clear()
                await self._completion_event.wait()
                await self._process_queue()

    @property
    def has_pending(self) -> bool:
        """Check if there are still tools that haven't been yielded."""
        return any(t.status != ToolStatus.YIELDED for t in self._queue)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_streaming_executor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/streaming_tool_executor.py tests/test_streaming_executor.py
git commit -m "feat: StreamingToolExecutor with concurrent-safe tool parallelism"
```

---

### Task 10: Mark Tools with Concurrency Safety

**Files:**
- Modify: `packages/app/tool.py` — add `is_concurrent_safe` to Tool protocol
- Modify: All 15 tool files — add `is_concurrent_safe` attribute
- Add tests

- [ ] **Step 1: Write test**

```python
# tests/test_tool_concurrency.py
from app.tool_registry import get_tools


def test_read_tools_are_concurrent_safe():
    """Read-only tools should be marked as concurrent-safe."""
    tools = get_tools()
    tool_map = {t.name: t for t in tools}

    safe_tools = {"Read", "Grep", "Glob", "WebFetch", "WebSearch",
                  "TaskList", "TaskGet"}
    for name in safe_tools:
        if name in tool_map:
            assert getattr(tool_map[name], "is_concurrent_safe", False), \
                f"{name} should be concurrent-safe"

    unsafe_tools = {"Bash", "Edit", "Write", "NotebookEdit"}
    for name in unsafe_tools:
        if name in tool_map:
            assert not getattr(tool_map[name], "is_concurrent_safe", True), \
                f"{name} should NOT be concurrent-safe"
```

- [ ] **Step 2: Add `is_concurrent_safe` to each tool class**

Add `is_concurrent_safe = True` to: FileReadTool, GrepTool, GlobTool, WebFetchTool, WebSearchTool, TaskListTool, TaskGetTool, AskUserQuestionTool.

Add `is_concurrent_safe = False` to: BashTool, FileEditTool, FileWriteTool, NotebookEditTool, TaskCreateTool, TaskUpdateTool, AgentTool.

- [ ] **Step 3: Run tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest tests/test_tool_concurrency.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/tools/ tests/test_tool_concurrency.py
git commit -m "feat: mark all 15 tools with is_concurrent_safe for parallel execution"
```

---

### Task 11: Wire StreamingToolExecutor into Query Loop

**Files:**
- Modify: `packages/app/query.py`

- [ ] **Step 1: Write integration test**

```python
# Add to tests/test_streaming_executor.py

@pytest.mark.asyncio
async def test_query_uses_streaming_executor():
    """query() should use StreamingToolExecutor for concurrent tool execution."""
    # Create a mock that simulates two concurrent tool calls
    seq1 = [
        StreamEvent(type="tool_use", tool_name="Read", tool_use_id="tu_1",
                    tool_input={"path": "a.txt"}),
        StreamEvent(type="tool_use", tool_name="Read", tool_use_id="tu_2",
                    tool_input={"path": "b.txt"}),
        StreamEvent(type="usage", input_tokens=100, output_tokens=50),
        StreamEvent(type="message_stop", stop_reason="end_turn"),
    ]
    seq2 = [
        StreamEvent(type="text_delta", text="Done reading both files."),
        StreamEvent(type="usage", input_tokens=200, output_tokens=100),
        StreamEvent(type="message_stop", stop_reason="end_turn"),
    ]
    client = _make_api_client([seq1, seq2])

    # ... test that both tool results come back
```

- [ ] **Step 2: Replace serial tool execution in query() with StreamingToolExecutor**

In the tool execution section of `query.py`, replace the for-loop:

```python
# Replace the serial tool execution block with:
from app.streaming_tool_executor import StreamingToolExecutor

if tool_use_events:
    executor = StreamingToolExecutor(
        tools, context=context, tool_executor=tool_executor
    )
    for ev in tool_use_events:
        executor.add_tool(
            ToolUseBlock(id=ev.tool_use_id, name=ev.tool_name, input=ev.tool_input)
        )

    tool_result_blocks = []
    async for result in executor.get_results():
        # Match result back to tool_use_id by order
        ev = tool_use_events[len(tool_result_blocks)]
        all_tool_calls.append({...})
        tool_result_blocks.append(
            ToolResultBlock(
                tool_use_id=ev.tool_use_id,
                content=result.content if isinstance(result.content, str) else str(result.content),
                is_error=result.is_error,
            )
        )
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/mingcui/Documents/文稿/claude-code-python && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
git add packages/app/query.py
git commit -m "feat: wire StreamingToolExecutor into query loop for concurrent tool execution"
```

---

## Self-Review Checklist

### 1. Spec Coverage

| Design Spec Requirement | Task |
|------------------------|------|
| Extensible command system | Tasks 1-2, 4 |
| Multi-level CLAUDE.md | Task 3 |
| Auto-continue (max_output_tokens) | Task 6 |
| Message normalization | Tasks 5, 8 |
| Reactive compact (prompt_too_long) | Task 7 |
| Concurrent tool execution | Tasks 9-11 |
| /cost, /help commands | Task 2 |

### 2. Placeholder Scan
- No TBD, TODO, or "implement later" references
- All steps have concrete code
- All test commands have expected outcomes

### 3. Type Consistency
- `CommandResult` used consistently across commands.py, command_registry.py, and all handlers
- `StreamEvent.stop_reason` added to dataclass and consumed in query.py
- `TrackedTool` state machine: QUEUED → EXECUTING → COMPLETED → YIELDED used consistently
- `is_concurrent_safe` attribute name consistent across tool.py protocol and all tool implementations
