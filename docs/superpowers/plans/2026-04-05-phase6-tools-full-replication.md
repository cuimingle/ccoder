# Phase 6: Tools System Full Replication

> **Goal:** Fully replicate the TypeScript Claude Code tool system — including Tool protocol, all tool implementations (with exact prompts & schemas), tool registry, deferred loading, and tool search.

---

## 1. Current State vs Target

### 1.1 Tool Protocol Gap

**Current Python `Tool` Protocol (tool.py):**
```python
class Tool(Protocol):
    name: str
    description: str          # Static string
    input_schema: dict
    def is_enabled(self) -> bool: ...
    async def call(self, input: dict, context: ToolContext) -> ToolResult: ...
    def render_result(self, result: ToolResult) -> str: ...
```

**TS `Tool<Input, Output>` has 40+ fields.** We need to replicate the **functionally critical** ones:

| TS Field | Status | Priority |
|----------|--------|----------|
| `name: string` | ✅ Exists | — |
| `aliases?: string[]` | ❌ Missing | P1 |
| `searchHint?: string` | ❌ Missing | P2 (for ToolSearch) |
| `prompt(options): Promise<string>` | ❌ Missing (only static `description`) | **P0** |
| `inputSchema` (Zod) | ✅ Exists as dict | Needs alignment |
| `isReadOnly(input): bool` | ⚠️ Static `readonly` attr | P1 — make input-dependent |
| `isConcurrencySafe(input): bool` | ⚠️ Static attr | P1 — make input-dependent |
| `isDestructive?(input): bool` | ❌ Missing | P2 |
| `isEnabled(): bool` | ✅ Exists | — |
| `checkPermissions(input, ctx)` | ❌ Missing (in ToolExecutor) | P1 |
| `validateInput?(input, ctx)` | ❌ Missing | P1 |
| `shouldDefer?: bool` | ❌ Missing | P2 (for ToolSearch) |
| `alwaysLoad?: bool` | ❌ Missing | P2 |
| `userFacingName(input): str` | ❌ Missing | P2 |
| `getActivityDescription?(input)` | ❌ Missing | P2 |
| `renderToolUseMessage(input)` | ❌ Missing (only `render_result`) | P2 |
| `maxResultSizeChars` | ❌ Missing | P2 |

### 1.2 Tool Inventory Gap

**Existing Python tools (15):**

| # | Tool | Prompt Aligned? | Schema Aligned? | Logic Complete? |
|---|------|----------------|-----------------|-----------------|
| 1 | Bash | ❌ Simplified | ❌ Missing `description`, `run_in_background`, `dangerouslyDisableSandbox` | ⚠️ Basic |
| 2 | Read | ❌ Simplified | ❌ Missing `pages` (PDF) | ⚠️ No PDF/image |
| 3 | Edit | ❌ Simplified | ✅ Mostly aligned | ✅ OK |
| 4 | Write | ❌ Simplified | ✅ Aligned | ✅ OK |
| 5 | Glob | ❌ Simplified | ✅ Aligned | ✅ OK |
| 6 | Grep | ❌ Simplified | ❌ Missing `-A/-B/-C/-n/-i`, `type`, `head_limit`, `offset`, `multiline` | ⚠️ Basic |
| 7 | WebFetch | ❌ Simplified | ⚠️ `prompt` required in TS | ⚠️ No cache, no sub-model |
| 8 | WebSearch | ❌ Simplified | ❌ Missing `blocked_domains` | ⚠️ Basic |
| 9 | AskUserQuestion | ❌ Simplified | ⚠️ Missing option `label`/`description`/`preview` details | ⚠️ Console-only |
| 10 | Agent | ❌ Simplified | ❌ Missing `subagent_type`, `model`, `run_in_background`, `isolation` | ⚠️ Basic |
| 11 | NotebookEdit | ❌ Simplified | ⚠️ Uses `cell_number` not `cell_id` | ✅ OK |
| 12 | TaskCreate | ❌ Simplified | ❌ Missing `metadata` | ✅ OK |
| 13 | TaskUpdate | ❌ Simplified | ❌ Missing `description`, `activeForm`, `addBlocks`, `addBlockedBy`, `metadata` | ⚠️ Basic |
| 14 | TaskList | ❌ Simplified | ✅ | ✅ OK |
| 15 | TaskGet | ❌ Simplified | ✅ | ✅ OK |

**Missing tools (need to add):**

| # | Tool | Priority | Complexity |
|---|------|----------|------------|
| 16 | TaskStop | P1 | Low |
| 17 | TaskOutput | P1 | Low |
| 18 | SkillTool | P1 | Medium |
| 19 | EnterPlanMode | P1 | Low |
| 20 | ExitPlanMode | P1 | Medium |
| 21 | ToolSearch | P1 | Medium |
| 22 | EnterWorktree | P2 | Medium |
| 23 | ExitWorktree | P2 | Medium |
| 24 | CronCreate | P2 | Medium |
| 25 | CronList | P2 | Low |
| 26 | CronDelete | P2 | Low |
| 27 | SendMessage | P2 | Medium |
| 28 | RemoteTrigger | P3 | Medium |
| 29 | LSPTool | P3 | High |
| 30 | MCPTool | P3 | High |
| 31 | ListMcpResources | P3 | Low |
| 32 | ReadMcpResource | P3 | Low |
| 33 | McpAuth | P3 | Medium |
| 34 | ConfigTool | P3 | Medium |
| 35 | BriefTool | P3 | Low |
| 36 | PowerShellTool | P3 (Windows) | Low (like Bash) |

---

## 2. Implementation Plan

### Phase 6A: Tool Protocol Enhancement

**File:** `packages/app/tool.py`

Upgrade the Tool Protocol to match TS capabilities:

```python
"""Tool Protocol definition and utilities."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Any, Callable, Awaitable
from enum import Enum


@dataclass
class ToolResult:
    """Result from a tool execution."""
    content: str | list[dict]
    is_error: bool = False


@dataclass
class ToolContext:
    """Context passed to each tool call."""
    cwd: str
    permission_mode: str = "manual"
    session_id: str = ""
    # Extensible: add fields as needed without breaking existing tools
    read_file_state: dict | None = None      # LRU cache for Read-before-Edit
    abort_signal: Any = None                  # For cancellation
    on_progress: Callable | None = None       # Progress callback


@runtime_checkable
class Tool(Protocol):
    """Tool interface matching TS Tool<Input, Output>."""
    name: str
    input_schema: dict

    # --- Optional class-level attributes with defaults ---
    # aliases: list[str]        # Alternative names
    # search_hint: str          # For ToolSearch keyword matching
    # should_defer: bool        # Deferred tool (needs ToolSearch to activate)
    # always_load: bool         # Never defer
    # max_result_size_chars: int  # Threshold for disk persistence

    def is_enabled(self) -> bool: ...
    def is_read_only(self, input: dict | None = None) -> bool: ...
    def is_concurrent_safe(self, input: dict | None = None) -> bool: ...

    async def prompt(self) -> str:
        """Full prompt text for the system message. Replaces static description."""
        ...

    async def call(self, input: dict, context: ToolContext) -> ToolResult: ...
    def render_result(self, result: ToolResult) -> str: ...

    # --- Optional methods (have defaults in BaseTool) ---
    # def is_destructive(self, input: dict) -> bool: ...
    # async def validate_input(self, input: dict, context: ToolContext) -> ValidationResult: ...
    # async def check_permissions(self, input: dict, context: ToolContext) -> PermissionResult: ...
    # def user_facing_name(self, input: dict | None = None) -> str: ...
    # def get_activity_description(self, input: dict) -> str | None: ...


class BaseTool:
    """Base class providing sensible defaults for all Tool protocol methods."""
    name: str = ""
    aliases: list[str] = []
    search_hint: str = ""
    input_schema: dict = {}
    should_defer: bool = False
    always_load: bool = False
    max_result_size_chars: int = 100_000

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def prompt(self) -> str:
        """Override to provide the full system prompt for this tool."""
        return ""

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        raise NotImplementedError

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)

    def user_facing_name(self, input: dict | None = None) -> str:
        return self.name

    def get_activity_description(self, input: dict) -> str | None:
        return None

    def is_destructive(self, input: dict | None = None) -> bool:
        return False

    async def validate_input(self, input: dict, context: ToolContext) -> dict:
        """Returns {"result": True} or {"result": False, "message": str}."""
        return {"result": True}


def find_tool_by_name(tools: list, name: str):
    """Find a tool by name or alias."""
    for tool in tools:
        if tool.name == name:
            return tool
        if hasattr(tool, 'aliases') and name in tool.aliases:
            return tool
    return None
```

**Key changes:**
- `description` → `prompt()` async method (returns full prompt string)
- `readonly` / `is_concurrent_safe` → methods that take `input` (input-dependent)
- Add `BaseTool` class as default implementation (not required, but convenient)
- Add `aliases`, `search_hint`, `should_defer` for ToolSearch
- Add `validate_input`, `is_destructive`, `user_facing_name`, `get_activity_description`

---

### Phase 6B: Align Existing 15 Tools (Prompts + Schemas + Logic)

For each existing tool, we need to:
1. Replace simplified `description` with exact TS `prompt()` text
2. Align `input_schema` to exact TS fields
3. Fix `is_read_only()` / `is_concurrent_safe()` to match TS behavior
4. Enhance implementation where needed

#### 6B.1 — BashTool

**File:** `packages/app/tools/bash_tool.py`

**Changes:**
- Add exact TS prompt (very long, ~3000 chars, covers git workflow, command guidelines, etc.)
- Add `description`, `timeout` (ms not s), `run_in_background`, `dangerouslyDisableSandbox` to schema
- `is_read_only(input)` — analyze command for read-only patterns
- `is_concurrent_safe()` → `True` (TS default)
- Add background task support
- Max timeout: 600000ms (10 min)

```python
class BashTool(BaseTool):
    name = "Bash"

    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command to execute"
            },
            "description": {
                "type": "string",
                "description": (
                    "Clear, concise description of what this command does in active voice. "
                    "Never use words like \"complex\" or \"risk\" in the description - "
                    "just describe what it does.\n\n"
                    "For simple commands (git, npm, standard CLI tools), keep it brief (5-10 words):\n"
                    "- ls → \"List files in current directory\"\n"
                    "- git status → \"Show working tree status\"\n"
                    "- npm install → \"Install package dependencies\"\n\n"
                    "For commands that are harder to parse at a glance (piped commands, obscure flags, etc.), "
                    "add enough context to clarify what it does:\n"
                    "- find . -name \"*.tmp\" -exec rm {} \\; → \"Find and delete all .tmp files recursively\"\n"
                    "- git reset --hard origin/main → \"Discard all local changes and match remote main\"\n"
                    "- curl -s url | jq '.data[]' → \"Fetch JSON from URL and extract data array elements\""
                )
            },
            "timeout": {
                "type": "number",
                "description": "Optional timeout in milliseconds (max 600000)"
            },
            "run_in_background": {
                "type": "boolean",
                "description": (
                    "Set to true to run this command in the background. "
                    "Use Read to read the output later."
                )
            },
        },
        "required": ["command"],
    }

    async def prompt(self) -> str:
        return BASH_PROMPT  # Full TS prompt text (see below)

    def is_read_only(self, input: dict | None = None) -> bool:
        return False  # Conservative default; TS does command analysis

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True
```

**Full prompt text** — stored as module-level constant `BASH_PROMPT` (exact copy from TS `BashTool/prompt.ts`):

```
Executes a given bash command and returns its output.

The working directory persists between commands, but shell state does not. The shell environment is initialized from the user's profile (bash or zsh).

IMPORTANT: Avoid using this tool to run `find`, `grep`, `cat`, `head`, `tail`, `sed`, `awk`, or `echo` commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:

 - File search: Use Glob (NOT find or ls)
 - Content search: Use Grep (NOT grep or rg)
 - Read files: Use Read (NOT cat/head/tail)
 - Edit files: Use Edit (NOT sed/awk)
 - Write files: Use Write (NOT echo >/cat <<EOF)
 - Communication: Output text directly (NOT echo/printf)
While the Bash tool can do similar things, it's better to use the built-in tools as they provide a better user experience and make it easier to review tool calls and give permission.

# Instructions
 - If your command will create new directories or files, first use this tool to run `ls` to verify the parent directory exists and is the correct location.
 - Always quote file paths that contain spaces with double quotes in your command (e.g., cd "path with spaces/file.txt")
 - Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it.
 - You may specify an optional timeout in milliseconds (up to 600000ms / 10 minutes). By default, your command will timeout after 120000ms (2 minutes).
 - You can use the `run_in_background` parameter to run the command in the background. Only use this if you don't need the result immediately and are OK being notified when the command completes later. You do not need to check the output right away - you'll be notified when it finishes. You do not need to use '&' at the end of the command when using this parameter.
 - When issuing multiple commands:
  - If the commands are independent and can run in parallel, make multiple Bash tool calls in a single message. Example: if you need to run "git status" and "git diff", send a single message with two Bash tool calls in parallel.
  - If the commands depend on each other and must run sequentially, use a single Bash call with '&&' to chain them together.
  - Use ';' only when you need to run commands sequentially but don't care if earlier commands fail.
  - DO NOT use newlines to separate commands (newlines are ok in quoted strings).
 - For git commands:
  - Prefer to create a new commit rather than amending an existing commit.
  - Before running destructive operations (e.g., git reset --hard, git push --force, git checkout --), consider whether there is a safer alternative that achieves the same goal. Only use destructive operations when they are truly the best approach.
  - Never skip hooks (--no-verify) or bypass signing (--no-gpg-sign, -c commit.gpgsign=false) unless the user has explicitly asked for it. If a hook fails, investigate and fix the underlying issue.
 - Avoid unnecessary `sleep` commands:
  - Do not sleep between commands that can run immediately — just run them.
  - If your command is long running and you would like to be notified when it finishes — use `run_in_background`. No sleep needed.
  - Do not retry failing commands in a sleep loop — diagnose the root cause.
  - If waiting for a background task you started with `run_in_background`, you will be notified when it completes — do not poll.
  - If you must poll an external process, use a check command (e.g. `gh run view`) rather than sleeping first.
  - If you must sleep, keep the duration short (1-5 seconds) to avoid blocking the user.
```

*(Plus the full git commit / PR creation sections from TS prompt — ~2000 more chars)*

#### 6B.2 — FileReadTool (Read)

**Schema additions:** `pages` field for PDF support
**Prompt:** Full TS prompt (~800 chars)
**Logic:** Add PDF reading (via `pdfplumber` or `pymupdf`), image support (return base64), Jupyter notebook rendering

#### 6B.3 — FileEditTool (Edit)

**Prompt:** Full TS prompt with indentation preservation guidance
**Schema:** Aligned (add `description` fields to each property)
**Logic:** Add read-file-state tracking (require Read before Edit)

#### 6B.4 — FileWriteTool (Write)

**Prompt:** Full TS prompt
**Logic:** Add read-file-state tracking (require Read for existing files)

#### 6B.5 — GlobTool

**Prompt:** Full TS prompt
**Schema:** Aligned, add `path` description about omitting for default

#### 6B.6 — GrepTool

**Major schema expansion:**
```python
input_schema = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "The regular expression pattern to search for in file contents"},
        "path": {"type": "string", "description": "File or directory to search in (rg PATH). Defaults to current working directory."},
        "glob": {"type": "string", "description": "Glob pattern to filter files (e.g. \"*.js\", \"*.{ts,tsx}\") - maps to rg --glob"},
        "output_mode": {
            "type": "string",
            "enum": ["content", "files_with_matches", "count"],
            "description": "Output mode: \"content\" shows matching lines..., \"files_with_matches\" shows file paths..., \"count\" shows match counts.... Defaults to \"files_with_matches\"."
        },
        "-B": {"type": "number", "description": "Number of lines to show before each match (rg -B). Requires output_mode: \"content\", ignored otherwise."},
        "-A": {"type": "number", "description": "Number of lines to show after each match (rg -A). Requires output_mode: \"content\", ignored otherwise."},
        "-C": {"type": "number", "description": "Alias for context."},
        "context": {"type": "number", "description": "Number of lines to show before and after each match (rg -C). Requires output_mode: \"content\", ignored otherwise."},
        "-n": {"type": "boolean", "description": "Show line numbers in output (rg -n). Requires output_mode: \"content\", ignored otherwise. Defaults to true."},
        "-i": {"type": "boolean", "description": "Case insensitive search (rg -i)"},
        "type": {"type": "string", "description": "File type to search (rg --type). Common types: js, py, rust, go, java, etc."},
        "head_limit": {"type": "number", "description": "Limit output to first N lines/entries... Defaults to 250 when unspecified. Pass 0 for unlimited."},
        "offset": {"type": "number", "description": "Skip first N lines/entries before applying head_limit... Defaults to 0."},
        "multiline": {"type": "boolean", "description": "Enable multiline mode where . matches newlines and patterns can span lines (rg -U --multiline-dotall). Default: false."},
    },
    "required": ["pattern"],
}
```

**Logic:** Map all new fields to rg flags. Handle `head_limit` (default 250), `offset`, `multiline`.

#### 6B.7 — WebFetchTool

**Schema:** Make `prompt` required (matches TS)
**Prompt:** Full TS prompt (mentions MCP preference, cache, redirects)
**Logic:** Add 15-min cache, redirect handling, sub-model processing option

#### 6B.8 — WebSearchTool

**Schema:** Add `blocked_domains`
**Prompt:** Full TS prompt (mandatory Sources section)
**Logic:** Add blocked_domains filtering

#### 6B.9 — AskUserQuestionTool

**Schema:** Full alignment with TS option schema (label, description, preview)
**Prompt:** Full TS prompt

#### 6B.10 — AgentTool

**Major schema expansion:**
```python
input_schema = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "A short (3-5 word) description of the task"},
        "prompt": {"type": "string", "description": "The task for the agent to perform"},
        "subagent_type": {"type": "string", "description": "The type of specialized agent to use for this task"},
        "model": {
            "type": "string",
            "enum": ["sonnet", "opus", "haiku"],
            "description": "Optional model override for this agent."
        },
        "run_in_background": {"type": "boolean", "description": "Set to true to run this agent in the background."},
        "isolation": {
            "type": "string",
            "enum": ["worktree"],
            "description": "Isolation mode. \"worktree\" creates a temporary git worktree."
        },
    },
    "required": ["description", "prompt"],
}
```

**Prompt:** Full TS prompt (very long, ~3000 chars, covers agent types, concurrency, isolation, etc.)
**Logic:** Add background execution, model override, isolation support

#### 6B.11 — NotebookEditTool

**Schema:** Change `cell_number` to `cell_id` to match TS
**Prompt:** Full TS prompt

#### 6B.12-15 — Task Tools

**TaskCreate:** Add `metadata` field
**TaskUpdate:** Add `description`, `activeForm`, `addBlocks`, `addBlockedBy`, `metadata` fields
**All:** Full TS prompts (contain usage guidelines, when-to-use, etc.)

---

### Phase 6C: New Tool Implementations

#### 6C.1 — TaskStopTool

**File:** `packages/app/tools/task_tool.py` (add to existing)

```python
class TaskStopTool(BaseTool):
    name = "TaskStop"

    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string", "description": "The ID of the task to stop"},
        },
        "required": ["taskId"],
    }

    def is_read_only(self, input=None) -> bool:
        return False

    async def prompt(self) -> str:
        return "Stops a running background task by its ID."

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        # Find task, set status to 'completed' or 'stopped', cancel if running
        ...
```

#### 6C.2 — TaskOutputTool

**File:** `packages/app/tools/task_tool.py`

```python
class TaskOutputTool(BaseTool):
    name = "TaskOutput"

    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string", "description": "The ID of the task"},
        },
        "required": ["taskId"],
    }

    def is_read_only(self, input=None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        # Return accumulated output from background task
        ...
```

#### 6C.3 — SkillTool

**File:** `packages/app/tools/skill_tool.py` (new)

```python
class SkillTool(BaseTool):
    name = "Skill"
    search_hint = "execute skill slash command"

    input_schema = {
        "type": "object",
        "properties": {
            "skill": {"type": "string", "description": 'The skill name. E.g., "commit", "review-pr", or "pdf"'},
            "args": {"type": "string", "description": "Optional arguments for the skill"},
        },
        "required": ["skill"],
    }

    async def prompt(self) -> str:
        return SKILL_PROMPT  # Full TS prompt text

    def is_read_only(self, input=None) -> bool:
        return False  # Skills can write

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        skill_name = input_data["skill"]
        args = input_data.get("args", "")
        # Look up skill in command_registry or skill_registry
        # Execute as slash command, return result
        ...
```

#### 6C.4 — EnterPlanModeTool

**File:** `packages/app/tools/plan_mode_tool.py` (new)

```python
class EnterPlanModeTool(BaseTool):
    name = "EnterPlanMode"

    input_schema = {"type": "object", "properties": {}}

    async def prompt(self) -> str:
        return ENTER_PLAN_MODE_PROMPT

    def is_read_only(self, input=None) -> bool:
        return True  # Just switches mode

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        # Set context.permission_mode to "plan"
        # Return confirmation message
        return ToolResult(content="Entered plan mode. You can now explore and plan without making changes.")
```

#### 6C.5 — ExitPlanModeTool

```python
class ExitPlanModeTool(BaseTool):
    name = "ExitPlanMode"

    input_schema = {
        "type": "object",
        "properties": {
            "plan": {"type": "string", "description": "Your implementation plan"},
        },
        "required": ["plan"],
    }

    def is_read_only(self, input=None) -> bool:
        return False  # Transitions out of plan mode

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        # Present plan to user for approval
        # Wait for approval via permission callback
        # Return approval status
        ...
```

#### 6C.6 — ToolSearchTool

**File:** `packages/app/tools/tool_search_tool.py` (new)

```python
class ToolSearchTool(BaseTool):
    name = "ToolSearch"
    always_load = True  # Never defer this tool

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    'Query to find deferred tools. Use "select:<tool_name>" for direct selection, '
                    'or keywords to search.'
                )
            },
            "max_results": {
                "type": "number",
                "description": "Maximum number of results to return (default: 5)",
            },
        },
        "required": ["query", "max_results"],
    }

    def is_read_only(self, input=None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        query = input_data["query"]
        max_results = int(input_data.get("max_results", 5))
        # Parse query: "select:Read,Edit,Grep" vs keyword search
        # Match against deferred tools by name, aliases, search_hint
        # Return tool schemas in <functions> format
        ...
```

#### 6C.7 — EnterWorktreeTool

**File:** `packages/app/tools/worktree_tool.py` (new)

```python
class EnterWorktreeTool(BaseTool):
    name = "EnterWorktree"

    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Optional name for the worktree. Each segment may contain only letters, "
                    "digits, dots, underscores, and dashes; max 64 chars total."
                )
            },
        },
    }

    async def prompt(self) -> str:
        return ENTER_WORKTREE_PROMPT

    def is_read_only(self, input=None) -> bool:
        return False

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        import subprocess, uuid
        name = input_data.get("name", uuid.uuid4().hex[:8])
        worktree_base = Path(context.cwd) / ".claude" / "worktrees"
        worktree_path = worktree_base / name
        branch_name = f"worktree-{name}"
        # git worktree add <path> -b <branch>
        # Update context.cwd to worktree_path
        ...
```

#### 6C.8 — ExitWorktreeTool

```python
class ExitWorktreeTool(BaseTool):
    name = "ExitWorktree"

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["keep", "remove"],
                "description": '"keep" leaves the worktree on disk; "remove" deletes both.'
            },
            "discard_changes": {
                "type": "boolean",
                "description": "Required true when action is 'remove' and worktree has uncommitted changes."
            },
        },
        "required": ["action"],
    }
```

#### 6C.9-11 — Cron Tools

**File:** `packages/app/tools/cron_tool.py` (new)

```python
class CronCreateTool(BaseTool):
    name = "CronCreate"
    input_schema = {
        "type": "object",
        "properties": {
            "cron": {"type": "string", "description": "Standard 5-field cron expression in local time"},
            "prompt": {"type": "string", "description": "Prompt to enqueue at fire time"},
            "recurring": {"type": "boolean", "description": "true (default) for recurring, false for one-shot"},
            "durable": {"type": "boolean", "description": "true to persist to disk, false (default) for session-only"},
        },
        "required": ["cron", "prompt"],
    }

class CronListTool(BaseTool):
    name = "CronList"
    input_schema = {"type": "object", "properties": {}}
    def is_read_only(self, input=None) -> bool: return True

class CronDeleteTool(BaseTool):
    name = "CronDelete"
    input_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Job ID returned by CronCreate"},
        },
        "required": ["id"],
    }
```

#### 6C.12 — SendMessageTool

**File:** `packages/app/tools/send_message_tool.py` (new)

```python
class SendMessageTool(BaseTool):
    name = "SendMessage"
    input_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": 'Recipient: teammate name, or "*" for broadcast'},
            "summary": {"type": "string", "description": "5-10 word summary shown as preview"},
            "message": {"type": "string", "description": "Message content"},
        },
        "required": ["to", "message"],
    }
```

---

### Phase 6D: Tool Registry Enhancement

**File:** `packages/app/tool_registry.py`

```python
"""Tool registry — assembles and filters the tool pool."""
from __future__ import annotations
from app.tool import BaseTool, find_tool_by_name


def get_all_base_tools() -> list:
    """Complete exhaustive list of all tools."""
    from app.tools.bash_tool import BashTool
    from app.tools.file_read_tool import FileReadTool
    from app.tools.file_edit_tool import FileEditTool
    from app.tools.file_write_tool import FileWriteTool
    from app.tools.grep_tool import GrepTool
    from app.tools.glob_tool import GlobTool
    from app.tools.web_fetch_tool import WebFetchTool
    from app.tools.web_search_tool import WebSearchTool
    from app.tools.ask_user_tool import AskUserQuestionTool
    from app.tools.agent_tool import AgentTool
    from app.tools.notebook_edit_tool import NotebookEditTool
    from app.tools.task_tool import (
        TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool,
        TaskStopTool, TaskOutputTool,
    )
    from app.tools.skill_tool import SkillTool
    from app.tools.plan_mode_tool import EnterPlanModeTool, ExitPlanModeTool
    from app.tools.tool_search_tool import ToolSearchTool
    from app.tools.worktree_tool import EnterWorktreeTool, ExitWorktreeTool
    from app.tools.cron_tool import CronCreateTool, CronListTool, CronDeleteTool
    from app.tools.send_message_tool import SendMessageTool

    return [
        # Core tools (always loaded)
        BashTool(),
        FileReadTool(),
        FileEditTool(),
        FileWriteTool(),
        GrepTool(),
        GlobTool(),
        WebFetchTool(),
        WebSearchTool(),
        AskUserQuestionTool(),
        AgentTool(),
        NotebookEditTool(),
        # Task tools
        TaskCreateTool(),
        TaskUpdateTool(),
        TaskListTool(),
        TaskGetTool(),
        TaskStopTool(),
        TaskOutputTool(),
        # Planning tools
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        # Skill & search
        SkillTool(),
        ToolSearchTool(),
        # Worktree
        EnterWorktreeTool(),
        ExitWorktreeTool(),
        # Cron
        CronCreateTool(),
        CronListTool(),
        CronDeleteTool(),
        # Multi-agent
        SendMessageTool(),
    ]


def get_tools(permission_context: dict | None = None) -> list:
    """Return filtered, enabled tools for current context."""
    all_tools = get_all_base_tools()
    tools = [t for t in all_tools if t.is_enabled()]

    # Filter by deny rules if permission_context provided
    if permission_context:
        deny_rules = permission_context.get("deny_rules", [])
        tools = filter_tools_by_deny_rules(tools, deny_rules)

    # Sort by name for prompt-cache stability
    tools.sort(key=lambda t: t.name)
    return tools


def get_deferred_tools(tools: list) -> list:
    """Get tools that should be deferred (not included in initial prompt)."""
    return [t for t in tools if getattr(t, 'should_defer', False)]


def get_loaded_tools(tools: list) -> list:
    """Get tools that should be loaded in initial prompt."""
    return [t for t in tools if not getattr(t, 'should_defer', False)]


def filter_tools_by_deny_rules(tools: list, deny_rules: list) -> list:
    """Remove blanket-denied tools."""
    denied_names = set()
    for rule in deny_rules:
        if rule.get("pattern") is None or rule.get("pattern") == "":
            denied_names.add(rule.get("tool", ""))
    return [t for t in tools if t.name not in denied_names]
```

---

### Phase 6E: Prompt Integration into System Message

**File:** `packages/app/context.py` — update `build_system_prompt()` to call `await tool.prompt()` for each loaded tool.

The TS system prompt includes tool descriptions inline. We need to:

1. For **loaded tools**: Include full `prompt()` in system message
2. For **deferred tools**: Include only name + search_hint in a `<system-reminder>` block
3. Build the `<functions>` block with `input_schema` for loaded tools

```python
async def build_tools_system_section(tools: list) -> str:
    """Build the tools section of the system prompt."""
    loaded = get_loaded_tools(tools)
    deferred = get_deferred_tools(tools)

    sections = []
    for tool in loaded:
        prompt_text = await tool.prompt()
        if prompt_text:
            sections.append(f"## {tool.name}\n{prompt_text}")

    if deferred:
        deferred_list = ", ".join(t.name for t in deferred)
        sections.append(
            f"<system-reminder>\n"
            f"The following deferred tools are available via ToolSearch:\n"
            f"{deferred_list}\n"
            f"</system-reminder>"
        )

    return "\n\n".join(sections)
```

---

## 3. File Structure (Final)

```
packages/app/
├── tool.py                          # Enhanced Tool Protocol + BaseTool
├── tool_registry.py                 # Enhanced registry with deferred support
├── tool_executor.py                 # (existing, minor updates for validate_input)
├── streaming_tool_executor.py       # (existing, update is_concurrent_safe call)
├── tools/
│   ├── __init__.py
│   ├── bash_tool.py                 # ✏️ Full prompt + schema + background
│   ├── file_read_tool.py            # ✏️ Full prompt + PDF/image support
│   ├── file_edit_tool.py            # ✏️ Full prompt + read-state tracking
│   ├── file_write_tool.py           # ✏️ Full prompt + read-state tracking
│   ├── grep_tool.py                 # ✏️ Full prompt + all rg flags
│   ├── glob_tool.py                 # ✏️ Full prompt
│   ├── web_fetch_tool.py            # ✏️ Full prompt + cache + redirect
│   ├── web_search_tool.py           # ✏️ Full prompt + blocked_domains
│   ├── ask_user_tool.py             # ✏️ Full prompt + option schema
│   ├── agent_tool.py                # ✏️ Full prompt + subagent_type + background
│   ├── notebook_edit_tool.py        # ✏️ Full prompt + cell_id
│   ├── task_tool.py                 # ✏️ Full prompts + all fields + TaskStop + TaskOutput
│   ├── skill_tool.py                # 🆕 SkillTool
│   ├── plan_mode_tool.py            # 🆕 EnterPlanMode + ExitPlanMode
│   ├── tool_search_tool.py          # 🆕 ToolSearchTool
│   ├── worktree_tool.py             # 🆕 EnterWorktree + ExitWorktree
│   ├── cron_tool.py                 # 🆕 CronCreate + CronList + CronDelete
│   └── send_message_tool.py         # 🆕 SendMessageTool
```

---

## 4. Implementation Order

| Step | Scope | Est. | Depends On |
|------|-------|------|------------|
| **6A** | Tool Protocol + BaseTool | — | None |
| **6B.1** | BashTool full alignment | — | 6A |
| **6B.2** | FileReadTool (+ PDF) | — | 6A |
| **6B.3** | FileEditTool | — | 6A |
| **6B.4** | FileWriteTool | — | 6A |
| **6B.5** | GlobTool | — | 6A |
| **6B.6** | GrepTool (major) | — | 6A |
| **6B.7** | WebFetchTool | — | 6A |
| **6B.8** | WebSearchTool | — | 6A |
| **6B.9** | AskUserQuestionTool | — | 6A |
| **6B.10** | AgentTool (major) | — | 6A |
| **6B.11** | NotebookEditTool | — | 6A |
| **6B.12-15** | Task tools alignment | — | 6A |
| **6C.1-2** | TaskStop + TaskOutput | — | 6A |
| **6C.3** | SkillTool | — | 6A + command_registry |
| **6C.4-5** | PlanMode tools | — | 6A |
| **6C.6** | ToolSearchTool | — | 6A + 6D |
| **6C.7-8** | Worktree tools | — | 6A |
| **6C.9-11** | Cron tools | — | 6A |
| **6C.12** | SendMessageTool | — | 6A |
| **6D** | Registry enhancement | — | 6A + all tools |
| **6E** | System prompt integration | — | 6D |

---

## 5. Exact Prompt Texts Reference

All prompt texts should be copied verbatim from the TS source. The key files:

| Tool | TS Prompt Source |
|------|-----------------|
| Bash | `/tools/BashTool/prompt.ts` |
| Read | `/tools/FileReadTool/prompt.ts` |
| Edit | `/tools/FileEditTool/prompt.ts` |
| Write | `/tools/FileWriteTool/prompt.ts` |
| Glob | `/tools/GlobTool/prompt.ts` |
| Grep | `/tools/GrepTool/prompt.ts` |
| WebSearch | `/tools/WebSearchTool/prompt.ts` |
| WebFetch | `/tools/WebFetchTool/prompt.ts` |
| Agent | `/tools/AgentTool/prompt.ts` |
| AskUser | `/tools/AskUserQuestionTool/AskUserQuestionTool.tsx` |
| NotebookEdit | `/tools/NotebookEditTool/prompt.ts` |
| TaskCreate | `/tools/TaskCreateTool/prompt.ts` |
| TaskUpdate | `/tools/TaskUpdateTool/prompt.ts` |
| TaskList | `/tools/TaskListTool/prompt.ts` |
| TaskGet | `/tools/TaskGetTool/prompt.ts` |
| TaskStop | `/tools/TaskStopTool/TaskStopTool.ts` |
| Skill | `/tools/SkillTool/prompt.ts` |
| EnterPlanMode | `/tools/EnterPlanModeTool/prompt.ts` |
| ExitPlanMode | `/tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts` |
| ToolSearch | `/tools/ToolSearchTool/prompt.ts` |
| EnterWorktree | `/tools/EnterWorktreeTool/prompt.ts` |
| ExitWorktree | `/tools/ExitWorktreeTool/prompt.ts` |
| CronCreate | `/tools/ScheduleCronTool/prompt.ts` |
| SendMessage | `/tools/SendMessageTool/prompt.ts` |

**Implementation rule:** Each Python tool file should have a module-level `_PROMPT` constant containing the exact TS prompt text. The `prompt()` method returns this constant. Dynamic parts (like current date, model name) are interpolated at call time.

---

## 6. Testing Strategy

For each tool:
1. **Unit test prompt text** — verify `await tool.prompt()` returns non-empty string containing key phrases
2. **Unit test schema** — verify `input_schema` has correct required fields and types
3. **Unit test is_read_only / is_concurrent_safe** — verify correct values
4. **Integration test call()** — test with valid and invalid inputs
5. **Registry test** — verify tool appears in `get_tools()` output

New test files:
- `tests/tools/test_skill_tool.py`
- `tests/tools/test_plan_mode_tool.py`
- `tests/tools/test_tool_search_tool.py`
- `tests/tools/test_worktree_tool.py`
- `tests/tools/test_cron_tool.py`
- `tests/tools/test_send_message_tool.py`
- `tests/test_tool_protocol.py` (BaseTool defaults, find_tool_by_name with aliases)
- `tests/test_tool_registry_enhanced.py` (deferred filtering, deny rules)
