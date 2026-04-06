# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python implementation of the Claude Code CLI — an AI coding assistant with streaming API integration, a Textual TUI, extensible tool system, and permission/hook infrastructure.

## Development Commands

```bash
# Install dependencies
uv sync

# Run the CLI
uv run claude-code

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/tools/test_bash_tool.py -x -v

# Run a specific test
uv run pytest tests/tools/test_bash_tool.py::test_function_name -x -v
```

**Python version:** 3.13 (see `.python-version`)
**Package manager:** uv
**Build backend:** hatchling

## Architecture

### Entry point & CLI flow

`cli.py` → `main.py` (Click CLI) → two modes:
- **Interactive:** Launches `ClaudeCodeApp` (Textual TUI in `screens/repl.py`)
- **Pipe mode** (`--print` or stdin): Single non-interactive query

### Core query loop

`QueryEngine` (session orchestrator) → `query()` (single turn with streaming + tool loop):
1. Calls Claude API with streaming via `ClaudeAPIClient`
2. Collects text/tool-use events from stream
3. Executes tool calls → appends results → loops until model responds with text only
4. Handles auto-continuation on `max_output_tokens` (up to 3 times)
5. Handles reactive compaction on `prompt_too_long` errors

### Tool system

Tools implement the `Tool` Protocol (`tool.py`): `name`, `description`, `input_schema`, `call()`, `render_result()`. All tools are registered in `tool_registry.py`. Each tool has `is_read_only` and `is_concurrent_safe` flags.

Execution pipeline: `ToolExecutor` checks permissions → runs pre-hooks → calls tool → runs post-hooks.

### Permissions

Three modes (`PermissionMode` enum):
- **PLAN:** Read-only tools only
- **AUTO:** Deny rules → allow rules → deny (no user prompt)
- **MANUAL:** Deny rules → allow rules → ask user via TUI

Rules use `ToolName(pattern)` format with fnmatch globs. Configured in `settings.json` under `permissions.allow` / `permissions.deny`.

### Settings & hooks

Settings loaded from `~/.claude/settings.json` (user) and `.claude/settings.json` (project). Hooks (`PreToolUse`, `PostToolUse`) run shell commands matched by tool name pattern.

### Conversation management

- **Auto-compact:** Triggers at 90% of context window; micro-compacts long tool results first, then full compaction via summarization
- **CLAUDE.md hierarchy:** Loads from `~/.claude/CLAUDE.md`, `.claude/CLAUDE.md`, and `./CLAUDE.md` (deduped by resolved path)

### Commands

Slash commands (`/clear`, `/compact`, `/cost`, `/help`) registered in `command_registry.py`. Two types: `LocalCommand` (executes locally) and `PromptCommand` (generates prompt for model).

## Key patterns

- **AsyncIO throughout:** All I/O (subprocess, API, file) is async
- **Streaming by default:** API responses are streamed, never awaited in full
- **Protocol-based extensibility:** Tools use Python `Protocol`, not base classes
- **Dataclass message types:** `TextBlock`, `ToolUseBlock`, `ToolResultBlock` in `types/message.py`
