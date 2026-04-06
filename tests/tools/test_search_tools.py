"""Tests for GrepTool and GlobTool."""
from __future__ import annotations
import pytest
from pathlib import Path
from app.tools.grep_tool import GrepTool
from app.tools.glob_tool import GlobTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    print('hello')\n")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "README.md").write_text("# Project\nhello world\n")
    return tmp_path

# --- GrepTool ---

@pytest.mark.asyncio
async def test_grep_finds_pattern(project, ctx):
    result = await GrepTool().call({"pattern": "def hello", "path": str(project)}, ctx)
    assert result.is_error is False
    assert "main.py" in result.content

@pytest.mark.asyncio
async def test_grep_no_match_returns_empty(project, ctx):
    result = await GrepTool().call({"pattern": "nonexistent_xyz_pattern", "path": str(project)}, ctx)
    assert result.is_error is False
    assert result.content.strip() == "" or "no matches" in result.content.lower()

@pytest.mark.asyncio
async def test_grep_with_glob_filter(project, ctx):
    result = await GrepTool().call({
        "pattern": "def",
        "path": str(project),
        "glob": "*.py",
    }, ctx)
    assert "main.py" in result.content or "utils.py" in result.content

# --- GlobTool ---

@pytest.mark.asyncio
async def test_glob_finds_py_files(project, ctx):
    result = await GlobTool().call({"pattern": "**/*.py", "path": str(project)}, ctx)
    assert result.is_error is False
    assert "main.py" in result.content
    assert "utils.py" in result.content

@pytest.mark.asyncio
async def test_glob_finds_md_files(project, ctx):
    result = await GlobTool().call({"pattern": "*.md", "path": str(project)}, ctx)
    assert "README.md" in result.content

@pytest.mark.asyncio
async def test_glob_no_match(project, ctx):
    result = await GlobTool().call({"pattern": "**/*.xyz", "path": str(project)}, ctx)
    assert result.is_error is False
