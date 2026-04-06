"""Tool Protocol definition, BaseTool, and utilities.

Mirrors the TypeScript Tool<Input, Output> interface from Tool.ts.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Any, Callable


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
    read_file_state: dict | None = None      # LRU cache for Read-before-Edit tracking
    abort_signal: Any = None                  # For cancellation support
    on_progress: Callable | None = None       # Progress callback


@runtime_checkable
class Tool(Protocol):
    """Tool interface matching TS Tool<Input, Output>.

    Tools can be implemented either by subclassing BaseTool (recommended)
    or by implementing this Protocol directly.
    """
    name: str
    input_schema: dict

    def is_enabled(self) -> bool: ...
    def is_read_only(self, input: dict | None = None) -> bool: ...
    def is_concurrent_safe(self, input: dict | None = None) -> bool: ...
    async def prompt(self) -> str: ...
    async def call(self, input: dict, context: ToolContext) -> ToolResult: ...
    def render_result(self, result: ToolResult) -> str: ...


class BaseTool:
    """Base class providing sensible defaults for all Tool protocol methods.

    Subclass and override what you need. At minimum, set `name`, `input_schema`,
    implement `prompt()` and `call()`.
    """
    name: str = ""
    aliases: list[str] = []
    search_hint: str = ""          # 3-10 word capability phrase for ToolSearch matching
    input_schema: dict = {}
    should_defer: bool = False     # True = deferred tool, needs ToolSearch to activate
    always_load: bool = False      # True = never defer, always in initial prompt
    max_result_size_chars: int = 100_000

    # --- Required methods ---

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def prompt(self) -> str:
        """Full prompt text for the system message."""
        return ""

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        raise NotImplementedError

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)

    # --- Optional methods with defaults ---

    def user_facing_name(self, input: dict | None = None) -> str:
        return self.name

    def get_activity_description(self, input: dict | None = None) -> str | None:
        """Present-tense activity string, e.g. 'Reading src/foo.py'."""
        return None

    def is_destructive(self, input: dict | None = None) -> bool:
        """Whether tool performs irreversible operations (delete/overwrite/send)."""
        return False

    async def validate_input(self, input: dict, context: ToolContext) -> dict:
        """Validate input before execution.
        Returns {"result": True} or {"result": False, "message": str}.
        """
        return {"result": True}


def find_tool_by_name(tools: list, name: str):
    """Find a tool by name or alias. Returns None if not found."""
    for tool in tools:
        if tool.name == name:
            return tool
        if hasattr(tool, 'aliases') and name in getattr(tool, 'aliases', []):
            return tool
    return None
