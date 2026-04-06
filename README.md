<p align="center">
  <a href="README.md">English</a> |
  <a href="README_zh.md">简体中文</a>
</p>

# CCoder

A Python implementation of the Claude Code CLI — an AI coding assistant with streaming API integration, a Textual TUI, extensible tool system, and permission/hook infrastructure.

## Requirements

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager
- An Anthropic API key

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd ccoder

# Install dependencies
uv sync

# Set your API key and base URL
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_BASE_URL="https://api.anthropic.com"  # optional, for custom endpoints
```

## Usage

```bash
# Launch interactive TUI
uv run ccoder

# Pipe mode (non-interactive)
echo "Explain this code" | uv run ccoder --print

# One-shot query
uv run ccoder --print "What does this project do?"
```

## Development

```bash
# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/tools/test_bash_tool.py -x -v

# Run a specific test
uv run pytest tests/tools/test_bash_tool.py::test_function_name -x -v
```

## Features

### Core

- [x] **Streaming AI Conversations** — Real-time streaming responses from Claude API
- [x] **Interactive TUI** — Rich terminal interface built with [Textual](https://github.com/Textualize/textual)
- [x] **Pipe Mode** — Non-interactive mode for scripting (`--print` or stdin)
- [x] **Auto Compaction** — Smart context management with automatic conversation compaction
- [x] **Slash Commands** — Built-in commands (`/clear`, `/compact`, `/cost`, `/help`)

### Tool System

- [x] File read / write / edit
- [x] Bash command execution (with timeout & background mode)
- [x] Glob & Grep search (ripgrep integration)
- [x] Web fetch & search
- [x] Jupyter notebook editing
- [x] Agent orchestration & sub-agents
- [x] Task management
- [x] Git worktree management
- [x] Plan mode (enter / exit)
- [x] Cron scheduling
- [x] Tool search (deferred tool loading)

### Permission & Security

- [x] Three permission modes — Plan (read-only) / Auto (rule-based) / Manual (interactive)
- [x] Configurable allow/deny rules with fnmatch glob patterns
- [x] Sensitive path protection (~/.ssh, ~/.aws, etc.)
- [x] Pre/post tool-use hooks for custom shell commands

### Configuration

- [x] User-level settings (`~/.claude/settings.json`)
- [x] Project-level settings (`.claude/settings.json`)
- [x] CLAUDE.md instruction hierarchy (global / project / local)

### Planned

- [ ] MCP (Model Context Protocol) server support
- [ ] Conversation history persistence & resume
- [ ] Multi-model support (model switching at runtime)
- [ ] Plugin / extension system
- [ ] IDE integration (VS Code / JetBrains extensions)
- [ ] Custom TUI themes
- [ ] OAuth authentication
- [ ] i18n / localization

## Architecture

```
cli.py → main.py (Click CLI)
  ├── Interactive: ClaudeCodeApp (Textual TUI)
  └── Pipe mode: Single non-interactive query

QueryEngine (session orchestrator)
  → query() (single turn with streaming + tool loop)
    1. Call Claude API with streaming
    2. Collect text/tool-use events
    3. Execute tool calls → append results → loop
    4. Auto-continue on max_output_tokens
    5. Reactive compaction on prompt_too_long
```

### Key Components

| Component | Description |
|---|---|
| `app/query_engine.py` | Session orchestrator, manages conversation flow |
| `app/query/loop.py` | Core query loop with streaming and tool execution |
| `app/services/api/` | Claude API client with retry and streaming |
| `app/tools/` | All built-in tool implementations |
| `app/tool.py` | Tool Protocol definition |
| `app/permissions.py` | Permission checking (Plan/Auto/Manual modes) |
| `app/hooks.py` | Pre/post tool-use hook execution |
| `app/compaction.py` | Context window management and compaction |
| `app/screens/repl.py` | Textual TUI screen |
| `app/settings.py` | Settings loader (~/.claude/settings.json) |

## Configuration

Settings are loaded from:
- `~/.claude/settings.json` (user-level)
- `.claude/settings.json` (project-level)

Permissions use `ToolName(pattern)` format with fnmatch globs, configured under `permissions.allow` / `permissions.deny`.

## License

MIT
