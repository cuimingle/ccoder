"""Tests for AgentTool."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.agent_tool import AgentTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path), session_id="test-session")

def test_agent_tool_name():
    assert AgentTool().name == "Agent"

def test_agent_tool_schema():
    schema = AgentTool().input_schema
    assert "description" in schema["properties"]
    assert "prompt" in schema["properties"]

@pytest.mark.asyncio
async def test_agent_tool_runs_subquery(ctx):
    from app.query import QueryResult
    mock_result = QueryResult(
        response_text="Sub-agent completed.",
        tool_calls=[],
        input_tokens=5,
        output_tokens=3,
        messages=[],
    )
    with patch("app.query_engine.QueryEngine") as MockEngine:
        engine_instance = MagicMock()
        engine_instance.run_turn = AsyncMock(return_value=mock_result)
        MockEngine.return_value = engine_instance

        result = await AgentTool().call({
            "description": "test agent",
            "prompt": "do something",
        }, ctx)

    assert result.is_error is False
    assert "Sub-agent completed." in result.content

@pytest.mark.asyncio
async def test_agent_tool_handles_error(ctx):
    with patch("app.query_engine.QueryEngine") as MockEngine:
        engine_instance = MagicMock()
        engine_instance.run_turn = AsyncMock(side_effect=Exception("sub-agent failed"))
        MockEngine.return_value = engine_instance

        result = await AgentTool().call({
            "description": "test agent",
            "prompt": "do something",
        }, ctx)

    assert result.is_error is True
    assert "sub-agent failed" in result.content
