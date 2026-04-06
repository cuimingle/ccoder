"""Tests for is_concurrent_safe and is_read_only on all tools.

Aligned with TS behavior where all tools are concurrent-safe by default,
and is_read_only/is_concurrent_safe are methods (not static attributes).
"""
from app.tool_registry import get_tools


def test_read_only_tools():
    """Read-only tools should return True for is_read_only()."""
    tools = get_tools()
    tool_map = {t.name: t for t in tools}
    read_only = {
        "Read", "Grep", "Glob", "TaskList", "TaskGet", "TaskOutput",
        "CronList", "ToolSearch", "EnterPlanMode", "WebFetch", "WebSearch",
    }
    for name in read_only:
        if name in tool_map:
            tool = tool_map[name]
            assert tool.is_read_only(), f"{name} should be read-only"


def test_write_tools_are_not_read_only():
    """Write tools should return False for is_read_only()."""
    tools = get_tools()
    tool_map = {t.name: t for t in tools}
    writable = {
        "Bash", "Edit", "Write", "NotebookEdit", "TaskCreate",
        "TaskUpdate", "Agent", "ExitPlanMode",
    }
    for name in writable:
        if name in tool_map:
            tool = tool_map[name]
            assert not tool.is_read_only(), f"{name} should NOT be read-only"


def test_all_tools_are_concurrent_safe():
    """All tools are concurrent-safe in the TS reference implementation."""
    tools = get_tools()
    for tool in tools:
        assert tool.is_concurrent_safe(), f"{tool.name} should be concurrent-safe"


def test_all_tools_have_prompt():
    """All tools must have a non-empty prompt."""
    import asyncio
    tools = get_tools()
    for tool in tools:
        prompt = asyncio.run(tool.prompt())
        assert isinstance(prompt, str), f"{tool.name} prompt should be a string"
        assert len(prompt) > 0, f"{tool.name} should have a non-empty prompt"
