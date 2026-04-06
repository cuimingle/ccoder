"""Tests for Anthropic API client."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.api.claude import ClaudeAPIClient, APIRequestParams, StreamEvent

def test_api_request_params_defaults():
    params = APIRequestParams(
        model="claude-opus-4-6",
        messages=[{"role": "user", "content": "hello"}],
        system="You are helpful.",
        tools=[],
    )
    assert params.model == "claude-opus-4-6"
    assert params.max_tokens == 8096
    assert params.stream is True


def test_stream_event_text():
    event = StreamEvent(type="text_delta", text="hello")
    assert event.type == "text_delta"
    assert event.text == "hello"


def test_stream_event_tool_use():
    event = StreamEvent(
        type="tool_use",
        tool_use_id="call_123",
        tool_name="BashTool",
        tool_input={"command": "ls"},
    )
    assert event.type == "tool_use"
    assert event.tool_name == "BashTool"


@pytest.mark.asyncio
async def test_client_build_request_params():
    client = ClaudeAPIClient(api_key="test_key")
    params = client.build_request_params(
        messages=[{"role": "user", "content": "hello"}],
        system="You are helpful.",
        tools=[],
    )
    assert params.model == "claude-opus-4-6"
    assert len(params.messages) == 1
