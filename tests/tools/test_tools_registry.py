"""Tests for the tool registry."""
from __future__ import annotations
import asyncio
import pytest
from app.tool_registry import get_tools, get_all_base_tools

EXPECTED_TOOL_NAMES = {
    "Agent",
    "AskUserQuestion",
    "Bash",
    "CronCreate",
    "CronDelete",
    "CronList",
    "Edit",
    "EnterPlanMode",
    "EnterWorktree",
    "ExitPlanMode",
    "ExitWorktree",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "SendMessage",
    "Skill",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskOutput",
    "TaskStop",
    "TaskUpdate",
    "ToolSearch",
    "WebFetch",
    "WebSearch",
    "Write",
}

def test_get_tools_returns_all_tools():
    tools = get_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES

def test_all_tools_are_enabled():
    tools = get_tools()
    for tool in tools:
        assert tool.is_enabled(), f"Tool {tool.name} should be enabled"

def test_all_tools_have_valid_schema():
    tools = get_tools()
    for tool in tools:
        assert isinstance(tool.input_schema, dict), f"{tool.name}.input_schema must be dict"
        assert tool.input_schema.get("type") == "object", f"{tool.name}.input_schema must have type=object"
        assert "properties" in tool.input_schema, f"{tool.name}.input_schema must have properties"

def test_all_tools_have_prompt():
    """All tools must have a non-empty prompt (replaces old description check)."""
    tools = get_tools()
    for tool in tools:
        prompt_text = asyncio.run(tool.prompt())
        assert isinstance(prompt_text, str), f"{tool.name} prompt must be a string"
        assert len(prompt_text) > 0, f"{tool.name} must have a non-empty prompt"

def test_tools_sorted_by_name():
    """get_tools() returns tools sorted by name for prompt-cache stability."""
    tools = get_tools()
    names = [t.name for t in tools]
    assert names == sorted(names)

def test_get_all_base_tools():
    """get_all_base_tools() returns all tool instances."""
    tools = get_all_base_tools()
    assert len(tools) == len(EXPECTED_TOOL_NAMES)
