"""Tests for query hardening — auto-continue and reactive compaction.

Tests exercise the QueryRunner via the convenience query() wrapper,
using mock deps to simulate API responses and compaction behavior.
"""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.query import query, QueryResult
from app.query.deps import ProductionDeps
from app.compaction import AutoCompactResult
from app.services.api.claude import StreamEvent, APIRequestParams
from app.services.api.errors import is_prompt_too_long
from app.types.message import UserMessage


def _make_mock_deps(event_sequences: list[list[StreamEvent]]) -> MagicMock:
    """Create mock QueryDeps that yields different event lists per call_model invocation."""
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
    # Expose call_index for assertions
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
async def test_auto_continue_on_max_output_tokens():
    """First call returns stop_reason='max_output_tokens', second returns 'end_turn'.
    Both text parts should appear in the final response_text."""
    deps = _make_mock_deps([
        [
            StreamEvent(type="text_delta", text="Part one"),
            StreamEvent(type="message_stop", stop_reason="max_output_tokens"),
        ],
        [
            StreamEvent(type="text_delta", text=" Part two"),
            StreamEvent(type="message_stop", stop_reason="end_turn"),
        ],
    ])
    client = _make_api_client()

    with patch("app.query.ProductionDeps", return_value=deps):
        result = await query(
            messages=[UserMessage(content="hello")],
            system="",
            tools=[],
            api_client=client,
            cwd="/tmp",
            max_continuations=3,
        )

    assert "Part one" in result.response_text
    assert "Part two" in result.response_text


@pytest.mark.asyncio
async def test_no_continue_on_normal_stop():
    """Single call with 'end_turn' should not trigger continuation."""
    deps = _make_mock_deps([
        [
            StreamEvent(type="text_delta", text="All done"),
            StreamEvent(type="message_stop", stop_reason="end_turn"),
        ],
    ])
    client = _make_api_client()

    with patch("app.query.ProductionDeps", return_value=deps):
        result = await query(
            messages=[UserMessage(content="hello")],
            system="",
            tools=[],
            api_client=client,
            cwd="/tmp",
            max_continuations=3,
        )

    assert result.response_text == "All done"
    assert deps._get_call_index() == 1


# ---------------------------------------------------------------------------
# is_prompt_too_long tests (moved to use the proper API errors module)
# ---------------------------------------------------------------------------


class TestIsPromptTooLong:
    """Unit tests for is_prompt_too_long from errors module."""

    def test_prompt_is_too_long_message(self):
        assert is_prompt_too_long(Exception("prompt is too long")) is True

    def test_prompt_too_long_error_code(self):
        assert is_prompt_too_long(Exception("prompt_too_long")) is True

    def test_unrelated_error(self):
        assert is_prompt_too_long(Exception("rate limit exceeded")) is False


# ---------------------------------------------------------------------------
# Reactive compact (prompt_too_long recovery) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reactive_compact_on_prompt_too_long():
    """First API call raises prompt_too_long, reactive_compact runs, second succeeds."""
    call_count = 0

    async def mock_call_model(params, abort_signal=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("prompt is too long")
        yield StreamEvent(type="text_delta", text="Recovered!")
        yield StreamEvent(type="message_stop", stop_reason="end_turn")

    deps = MagicMock()
    deps.call_model = mock_call_model
    deps.microcompact = MagicMock(side_effect=lambda msgs: msgs)
    deps.autocompact = AsyncMock(return_value=AutoCompactResult(
        was_compacted=False, consecutive_failures=0
    ))
    deps.uuid = MagicMock(return_value="test-uuid")
    client = _make_api_client()

    compacted_messages = [UserMessage(content="[summary] compacted")]

    with patch("app.query.ProductionDeps", return_value=deps), \
         patch(
             "app.query.loop.reactive_compact",
             new_callable=AsyncMock,
             return_value=(compacted_messages, 100, 50),
         ) as mock_compact:
        result = await query(
            messages=[UserMessage(content="hello")],
            system="system prompt",
            tools=[],
            api_client=client,
            cwd="/tmp",
        )

    mock_compact.assert_called_once()
    assert result.response_text == "Recovered!"
    assert call_count == 2


@pytest.mark.asyncio
async def test_non_prompt_error_surfaces_as_terminal():
    """Errors unrelated to prompt_too_long should result in MODEL_ERROR terminal."""
    async def mock_call_model(params, abort_signal=None):
        raise Exception("rate limit exceeded")
        yield  # noqa: unreachable — makes this an async generator

    deps = MagicMock()
    deps.call_model = mock_call_model
    deps.microcompact = MagicMock(side_effect=lambda msgs: msgs)
    deps.autocompact = AsyncMock(return_value=AutoCompactResult(
        was_compacted=False, consecutive_failures=0
    ))
    deps.uuid = MagicMock(return_value="test-uuid")
    client = _make_api_client()

    with patch("app.query.ProductionDeps", return_value=deps):
        result = await query(
            messages=[UserMessage(content="hello")],
            system="system prompt",
            tools=[],
            api_client=client,
            cwd="/tmp",
        )

    # MODEL_ERROR terminal — query() collects it
    assert result.terminal is not None
    assert result.terminal.reason.value == "model_error"
