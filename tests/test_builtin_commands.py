"""Tests for built-in slash commands (/clear, /compact, /cost, /help)."""
from __future__ import annotations

import pytest

from app.commands import build_default_registry


@pytest.fixture
def registry():
    return build_default_registry()


@pytest.mark.asyncio
async def test_clear_command(registry):
    result = await registry.execute("clear", "", {})
    assert result.handled is True
    assert "Session cleared" in result.text


@pytest.mark.asyncio
async def test_help_command(registry):
    ctx = {"registry": registry}
    result = await registry.execute("help", "", ctx)
    assert result.handled is True
    assert "/compact" in result.text
    assert "/clear" in result.text
    assert "/cost" in result.text
    assert "/help" in result.text


@pytest.mark.asyncio
async def test_cost_command(registry):
    ctx = {
        "total_input_tokens": 5000,
        "total_output_tokens": 1000,
        "turn_count": 3,
    }
    result = await registry.execute("cost", "", ctx)
    assert result.handled is True
    assert "5,000" in result.text
    assert "1,000" in result.text
    assert "3" in result.text


@pytest.mark.asyncio
async def test_help_alias(registry):
    """Alias 'h' should resolve to the help command."""
    ctx = {"registry": registry}
    result = await registry.execute("h", "", ctx)
    assert result.handled is True
    assert "Available commands" in result.text


@pytest.mark.asyncio
async def test_question_mark_alias(registry):
    """Alias '?' should also resolve to help."""
    ctx = {"registry": registry}
    result = await registry.execute("?", "", ctx)
    assert result.handled is True
    assert "Available commands" in result.text


@pytest.mark.asyncio
async def test_unknown_command(registry):
    result = await registry.execute("nonexistent", "", {})
    assert result.handled is False
    assert "Unknown command" in result.text
