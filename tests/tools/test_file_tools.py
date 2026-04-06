"""Tests for file operation tools."""
from __future__ import annotations
import pytest
from pathlib import Path
from app.tools.file_read_tool import FileReadTool
from app.tools.file_edit_tool import FileEditTool
from app.tools.file_write_tool import FileWriteTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

# --- FileReadTool ---

@pytest.mark.asyncio
async def test_file_read_basic(tmp_path, ctx):
    f = tmp_path / "hello.txt"
    f.write_text("hello world\n")
    result = await FileReadTool().call({"file_path": str(f)}, ctx)
    assert "hello world" in result.content
    assert result.is_error is False

@pytest.mark.asyncio
async def test_file_read_with_line_range(tmp_path, ctx):
    f = tmp_path / "lines.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    result = await FileReadTool().call({"file_path": str(f), "offset": 2, "limit": 2}, ctx)
    assert "line2" in result.content
    assert "line4" not in result.content

@pytest.mark.asyncio
async def test_file_read_not_found(ctx):
    result = await FileReadTool().call({"file_path": "/nonexistent/file.txt"}, ctx)
    assert result.is_error is True

# --- FileEditTool ---

@pytest.mark.asyncio
async def test_file_edit_replaces_string(tmp_path, ctx):
    f = tmp_path / "code.py"
    f.write_text("def foo():\n    return 1\n")
    result = await FileEditTool().call({
        "file_path": str(f),
        "old_string": "return 1",
        "new_string": "return 2",
    }, ctx)
    assert result.is_error is False
    assert f.read_text() == "def foo():\n    return 2\n"

@pytest.mark.asyncio
async def test_file_edit_old_string_not_found(tmp_path, ctx):
    f = tmp_path / "code.py"
    f.write_text("def foo(): pass\n")
    result = await FileEditTool().call({
        "file_path": str(f),
        "old_string": "nonexistent string",
        "new_string": "something",
    }, ctx)
    assert result.is_error is True

@pytest.mark.asyncio
async def test_file_edit_ambiguous_string(tmp_path, ctx):
    f = tmp_path / "dup.py"
    f.write_text("x = 1\nx = 1\n")
    result = await FileEditTool().call({
        "file_path": str(f),
        "old_string": "x = 1",
        "new_string": "x = 2",
    }, ctx)
    assert result.is_error is True
    assert "unique" in result.content.lower() or "multiple" in result.content.lower()

# --- FileWriteTool ---

@pytest.mark.asyncio
async def test_file_write_creates_file(tmp_path, ctx):
    f = tmp_path / "new_file.py"
    result = await FileWriteTool().call({
        "file_path": str(f),
        "content": "print('hello')\n",
    }, ctx)
    assert result.is_error is False
    assert f.read_text() == "print('hello')\n"

@pytest.mark.asyncio
async def test_file_write_overwrites_file(tmp_path, ctx):
    f = tmp_path / "existing.txt"
    f.write_text("old content\n")
    result = await FileWriteTool().call({
        "file_path": str(f),
        "content": "new content\n",
    }, ctx)
    assert result.is_error is False
    assert f.read_text() == "new content\n"

@pytest.mark.asyncio
async def test_file_write_creates_parent_dirs(tmp_path, ctx):
    f = tmp_path / "a" / "b" / "c.txt"
    result = await FileWriteTool().call({
        "file_path": str(f),
        "content": "deep file\n",
    }, ctx)
    assert result.is_error is False
    assert f.read_text() == "deep file\n"
