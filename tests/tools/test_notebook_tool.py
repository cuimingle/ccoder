"""Tests for NotebookEditTool."""
from __future__ import annotations
import pytest
import json
from pathlib import Path
from app.tools.notebook_edit_tool import NotebookEditTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

@pytest.fixture
def sample_notebook(tmp_path):
    """Create a sample notebook with 3 cells."""
    nb = {
        "cells": [
            {
                "cell_type": "code",
                "id": "cell-1",
                "source": ["print('hello')"],
                "metadata": {},
                "execution_count": None,
                "outputs": []
            },
            {
                "cell_type": "markdown",
                "id": "cell-2",
                "source": ["# Title"],
                "metadata": {}
            },
            {
                "cell_type": "code",
                "id": "cell-3",
                "source": ["x = 42"],
                "metadata": {},
                "execution_count": None,
                "outputs": []
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5
    }
    nb_path = tmp_path / "test.ipynb"
    nb_path.write_text(json.dumps(nb, indent=2))
    return nb_path

# --- NotebookEditTool ---

@pytest.mark.asyncio
async def test_notebook_edit_replace_cell(sample_notebook, ctx):
    """Test replacing a cell's content."""
    result = await NotebookEditTool().call({
        "notebook_path": str(sample_notebook),
        "cell_number": 0,
        "new_source": "print('goodbye')"
    }, ctx)
    assert result.is_error is False

    nb = json.loads(sample_notebook.read_text())
    assert nb["cells"][0]["source"] == ["print('goodbye')"]

@pytest.mark.asyncio
async def test_notebook_edit_insert_cell(sample_notebook, ctx):
    """Test inserting a new cell."""
    result = await NotebookEditTool().call({
        "notebook_path": str(sample_notebook),
        "cell_number": 0,
        "new_source": "y = 100",
        "edit_mode": "insert",
        "cell_type": "code"
    }, ctx)
    assert result.is_error is False

    nb = json.loads(sample_notebook.read_text())
    assert len(nb["cells"]) == 4
    assert nb["cells"][1]["source"] == ["y = 100"]

@pytest.mark.asyncio
async def test_notebook_edit_delete_cell(sample_notebook, ctx):
    """Test deleting a cell."""
    result = await NotebookEditTool().call({
        "notebook_path": str(sample_notebook),
        "cell_number": 1,
        "new_source": "",
        "edit_mode": "delete"
    }, ctx)
    assert result.is_error is False

    nb = json.loads(sample_notebook.read_text())
    assert len(nb["cells"]) == 2
    assert all(c["id"] != "cell-2" for c in nb["cells"])

@pytest.mark.asyncio
async def test_notebook_edit_file_not_found(ctx):
    """Test error when notebook file doesn't exist."""
    result = await NotebookEditTool().call({
        "notebook_path": "/nonexistent/notebook.ipynb",
        "cell_number": 0,
        "new_source": "test"
    }, ctx)
    assert result.is_error is True
    assert "not found" in result.content.lower()

@pytest.mark.asyncio
async def test_notebook_edit_negative_cell_number(sample_notebook, ctx):
    """Test error when cell_number is negative."""
    result = await NotebookEditTool().call({
        "notebook_path": str(sample_notebook),
        "cell_number": -1,
        "new_source": "test"
    }, ctx)
    assert result.is_error is True
    assert "negative" in result.content.lower()

@pytest.mark.asyncio
async def test_notebook_edit_cell_number_exceeds_range(sample_notebook, ctx):
    """Test error when cell_number exceeds valid range."""
    result = await NotebookEditTool().call({
        "notebook_path": str(sample_notebook),
        "cell_number": 10,
        "new_source": "test"
    }, ctx)
    assert result.is_error is True
    assert "out of range" in result.content.lower()

@pytest.mark.asyncio
async def test_notebook_edit_insert_empty_notebook(tmp_path, ctx):
    """Test inserting into an empty notebook."""
    nb = {
        "cells": [],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5
    }
    nb_path = tmp_path / "empty.ipynb"
    nb_path.write_text(json.dumps(nb, indent=2))

    result = await NotebookEditTool().call({
        "notebook_path": str(nb_path),
        "cell_number": 0,
        "new_source": "print('first cell')",
        "edit_mode": "insert",
        "cell_type": "code"
    }, ctx)
    assert result.is_error is False

    nb = json.loads(nb_path.read_text())
    assert len(nb["cells"]) == 1
    assert nb["cells"][0]["source"] == ["print('first cell')"]

