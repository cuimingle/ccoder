"""Tests for the core query loop."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock
from app.query import query, QueryResult
from app.tool import ToolResult, ToolContext
from app.types.message import UserMessage, AssistantMessage, TextBlock


class EchoTool:
    name = "EchoTool"
    description = "Echoes input back"
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(content=f"echo: {input['text']}")

    def render_result(self, result: ToolResult) -> str:
        return result.content


@pytest.mark.asyncio
async def test_query_returns_result_on_message_stop():
    """query() should collect text and return QueryResult when stream ends."""
    from app.services.api.claude import StreamEvent

    mock_client = MagicMock()

    async def mock_stream(params):
        yield StreamEvent(type="text_delta", text="Hello")
        yield StreamEvent(type="text_delta", text=" World")
        yield StreamEvent(type="message_stop")

    mock_client.stream = mock_stream
    mock_client.build_request_params = MagicMock(return_value=MagicMock(
        model="claude-opus-4-6", messages=[], system="", tools=[], max_tokens=8096
    ))
    mock_client.messages_to_api_format = MagicMock(return_value=[])
    mock_client.tools_to_api_format = MagicMock(return_value=[])

    messages = [UserMessage(content="say hello")]
    result = await query(
        messages=messages,
        system="You are helpful.",
        tools=[],
        api_client=mock_client,
        cwd="/tmp",
    )

    assert isinstance(result, QueryResult)
    assert result.response_text == "Hello World"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_query_executes_tool_call():
    """query() should execute tool calls and add results to messages."""
    import json
    from app.services.api.claude import StreamEvent

    mock_client = MagicMock()
    call_count = 0

    async def mock_stream(params):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: respond with a tool use
            yield StreamEvent(
                type="tool_use",
                tool_use_id="call_abc",
                tool_name="EchoTool",
                tool_input={"text": "hi"},
            )
            yield StreamEvent(type="message_stop")
        else:
            # Second call: respond with text after tool result
            yield StreamEvent(type="text_delta", text="Done!")
            yield StreamEvent(type="message_stop")

    mock_client.stream = mock_stream
    mock_client.build_request_params = MagicMock(return_value=MagicMock(
        model="claude-opus-4-6", messages=[], system="", tools=[], max_tokens=8096
    ))
    mock_client.messages_to_api_format = MagicMock(return_value=[])
    mock_client.tools_to_api_format = MagicMock(return_value=[])

    messages = [UserMessage(content="use echo tool")]
    result = await query(
        messages=messages,
        system="",
        tools=[EchoTool()],
        api_client=mock_client,
        cwd="/tmp",
    )

    assert result.response_text == "Done!"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool_name"] == "EchoTool"
