"""Tests for BashTool."""
from __future__ import annotations
import pytest
from app.tools.bash_tool import BashTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

@pytest.fixture
def tool():
    return BashTool()

def test_bash_tool_name(tool):
    assert tool.name == "Bash"

def test_bash_tool_is_enabled(tool):
    assert tool.is_enabled() is True

def test_bash_tool_has_input_schema(tool):
    assert "command" in tool.input_schema["properties"]

@pytest.mark.asyncio
async def test_bash_executes_command(tool, ctx):
    result = await tool.call({"command": "echo hello"}, ctx)
    assert "hello" in result.content
    assert result.is_error is False

@pytest.mark.asyncio
async def test_bash_captures_stderr(tool, ctx):
    result = await tool.call({"command": "echo error >&2; exit 1"}, ctx)
    assert result.is_error is True

@pytest.mark.asyncio
async def test_bash_timeout(tool, ctx):
    result = await tool.call({"command": "sleep 10", "timeout": 1}, ctx)
    assert result.is_error is True
    assert "timeout" in result.content.lower() or "timed out" in result.content.lower()

@pytest.mark.asyncio
async def test_bash_respects_cwd(tool, tmp_path, ctx):
    (tmp_path / "marker.txt").write_text("found")
    result = await tool.call({"command": "cat marker.txt"}, ctx)
    assert "found" in result.content
