"""Tests for AskUserQuestionTool."""
from __future__ import annotations
import pytest
from unittest.mock import patch
from app.tools.ask_user_tool import AskUserQuestionTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

def test_ask_user_tool_name():
    assert AskUserQuestionTool().name == "AskUserQuestion"

def test_ask_user_tool_schema():
    schema = AskUserQuestionTool().input_schema
    assert "questions" in schema["properties"]

@pytest.mark.asyncio
async def test_ask_user_presents_questions(ctx):
    tool = AskUserQuestionTool()
    questions = [
        {"question": "Which approach?", "header": "Approach",
         "options": [{"label": "A"}, {"label": "B"}], "multiSelect": False}
    ]
    with patch("builtins.input", return_value="1"):
        result = await tool.call({"questions": questions}, ctx)
    assert result.is_error is False
    assert '"A"' in result.content

@pytest.mark.asyncio
async def test_ask_user_handles_non_interactive(ctx, monkeypatch):
    """In non-interactive mode (pipe), returns default first option."""
    tool = AskUserQuestionTool()
    questions = [
        {"question": "Pick one", "header": "Choice",
         "options": [{"label": "Option1"}, {"label": "Option2"}], "multiSelect": False}
    ]
    # Simulate EOF on stdin
    with patch("builtins.input", side_effect=EOFError):
        result = await tool.call({"questions": questions}, ctx)
    assert result.is_error is False
