"""Tests for QueryEngine session management."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.query_engine import QueryEngine
from app.query import QueryResult
from app.types.message import UserMessage


@pytest.fixture
def engine(tmp_path):
    return QueryEngine(cwd=str(tmp_path), api_key="test_key")


def test_engine_initial_state(engine):
    assert engine.turn_count == 0
    assert engine.messages == []
    assert engine.total_input_tokens == 0
    assert engine.total_output_tokens == 0


@pytest.mark.asyncio
async def test_engine_run_turn_increments_count(engine, tmp_path):
    mock_result = QueryResult(
        response_text="Hello!",
        tool_calls=[],
        input_tokens=10,
        output_tokens=5,
        messages=[UserMessage(content="hi"), ],
    )

    with patch("app.query_engine.query", new=AsyncMock(return_value=mock_result)):
        result = await engine.run_turn("hi")

    assert engine.turn_count == 1
    assert result.response_text == "Hello!"


@pytest.mark.asyncio
async def test_engine_accumulates_tokens(engine):
    mock_result = QueryResult(
        response_text="Hi",
        tool_calls=[],
        input_tokens=100,
        output_tokens=50,
        messages=[],
    )

    with patch("app.query_engine.query", new=AsyncMock(return_value=mock_result)):
        await engine.run_turn("hello")
        await engine.run_turn("world")

    assert engine.total_input_tokens == 200
    assert engine.total_output_tokens == 100


def test_engine_clear_resets_state(engine):
    engine.turn_count = 5
    engine._total_usage.input_tokens = 1000
    engine.clear()
    assert engine.turn_count == 0
    assert engine.messages == []
    assert engine.total_input_tokens == 0


@pytest.mark.asyncio
async def test_engine_cost_command(engine):
    """Engine processes /cost and shows token info."""
    engine._total_usage.input_tokens = 5000
    engine._total_usage.output_tokens = 2000
    engine.turn_count = 3

    result = await engine.run_turn("/cost")

    assert "Session Cost Summary" in result.response_text
    assert "5,000" in result.response_text
    assert "2,000" in result.response_text
    assert "Turns:         3" in result.response_text
    assert result.tool_calls == []
    # /cost should not increment turn count or call query()
    assert engine.turn_count == 3


@pytest.mark.asyncio
async def test_engine_help_command(engine):
    """Engine processes /help and shows command list."""
    result = await engine.run_turn("/help")

    assert "Available commands:" in result.response_text
    assert "/cost" in result.response_text
    assert "/help" in result.response_text
    assert "/clear" in result.response_text
    assert "/compact" in result.response_text
    assert result.tool_calls == []
