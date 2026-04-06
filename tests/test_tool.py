"""Tests for Tool protocol and registry."""
from __future__ import annotations
import pytest
from app.tool import ToolResult, find_tool_by_name, ToolContext
from app.tool_registry import get_tools


class MockTool:
    name = "MockTool"
    description = "A mock tool for testing"
    input_schema = {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: "ToolContext") -> ToolResult:
        return ToolResult(content=f"mock result: {input['input']}")

    def render_result(self, result: ToolResult) -> str:
        return result.content


def test_tool_result_creation():
    result = ToolResult(content="hello")
    assert result.content == "hello"
    assert result.is_error is False


def test_tool_result_error():
    result = ToolResult(content="error!", is_error=True)
    assert result.is_error is True


def test_find_tool_by_name_found():
    tools = [MockTool()]
    found = find_tool_by_name(tools, "MockTool")
    assert found is not None
    assert found.name == "MockTool"


def test_find_tool_by_name_not_found():
    tools = [MockTool()]
    found = find_tool_by_name(tools, "NonExistentTool")
    assert found is None


def test_get_tools_returns_list():
    tools = get_tools()
    assert isinstance(tools, list)
    # Phase 6: 27 tools registered after full replication
    assert len(tools) == 27
