"""Tests for the core query loop."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.query import query, QueryResult
from app.compaction import AutoCompactResult
from app.services.api.claude import StreamEvent, APIRequestParams
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

    def is_read_only(self, input=None) -> bool:
        return True

    def is_concurrent_safe(self, input=None) -> bool:
        return True

    async def prompt(self) -> str:
        return "Echoes input"

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(content=f"echo: {input['text']}")

    def render_result(self, result: ToolResult) -> str:
        return result.content


def _make_mock_deps(event_sequences: list[list[StreamEvent]]) -> MagicMock:
    """Create mock QueryDeps that yields different event lists per call."""
    mock_deps = MagicMock()
    call_index = 0

    async def mock_call_model(params, abort_signal=None):
        nonlocal call_index
        seq = event_sequences[min(call_index, len(event_sequences) - 1)]
        call_index += 1
        for event in seq:
            yield event

    mock_deps.call_model = mock_call_model
    mock_deps.microcompact = MagicMock(side_effect=lambda msgs: msgs)
    mock_deps.autocompact = AsyncMock(return_value=AutoCompactResult(
        was_compacted=False, consecutive_failures=0
    ))
    mock_deps.uuid = MagicMock(return_value="test-uuid")
    mock_deps._get_call_index = lambda: call_index
    return mock_deps


def _make_api_client() -> MagicMock:
    """Create a mock API client for building request params."""
    mock_client = MagicMock()
    mock_client.model = "claude-opus-4-6"
    mock_client.build_request_params = MagicMock(return_value=APIRequestParams(
        model="claude-opus-4-6", messages=[], system="", tools=[]
    ))
    mock_client.messages_to_api_format = MagicMock(return_value=[])
    mock_client.tools_to_api_format = AsyncMock(return_value=[])
    return mock_client


@pytest.mark.asyncio
async def test_query_returns_result_on_message_stop():
    """query() should collect text and return QueryResult when stream ends."""
    deps = _make_mock_deps([
        [
            StreamEvent(type="text_delta", text="Hello"),
            StreamEvent(type="text_delta", text=" World"),
            StreamEvent(type="message_stop", stop_reason="end_turn"),
        ],
    ])
    client = _make_api_client()

    with patch("app.query.ProductionDeps", return_value=deps):
        result = await query(
            messages=[UserMessage(content="say hello")],
            system="You are helpful.",
            tools=[],
            api_client=client,
            cwd="/tmp",
        )

    assert isinstance(result, QueryResult)
    assert result.response_text == "Hello World"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_query_executes_tool_call():
    """query() should execute tool calls and add results to messages."""
    deps = _make_mock_deps([
        [
            StreamEvent(
                type="tool_use",
                tool_use_id="call_abc",
                tool_name="EchoTool",
                tool_input={"text": "hi"},
            ),
            StreamEvent(type="message_stop", stop_reason="end_turn"),
        ],
        [
            StreamEvent(type="text_delta", text="Done!"),
            StreamEvent(type="message_stop", stop_reason="end_turn"),
        ],
    ])
    client = _make_api_client()

    with patch("app.query.ProductionDeps", return_value=deps):
        result = await query(
            messages=[UserMessage(content="use echo tool")],
            system="",
            tools=[EchoTool()],
            api_client=client,
            cwd="/tmp",
        )

    assert result.response_text == "Done!"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool_name"] == "EchoTool"
