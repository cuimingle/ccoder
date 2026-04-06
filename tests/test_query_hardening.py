"""Tests for query hardening — auto-continue and reactive compaction."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.query import query, _is_prompt_too_long
from app.services.api.claude import StreamEvent
from app.types.message import UserMessage


def _make_api_client(event_sequences: list[list[StreamEvent]]) -> MagicMock:
    """Create a mock API client that yields different event lists per call.

    Each element in event_sequences is a list of StreamEvents for one call.
    Successive calls to stream() yield the next sequence.
    """
    mock_client = MagicMock()
    call_index = 0

    async def mock_stream(params):
        nonlocal call_index
        seq = event_sequences[min(call_index, len(event_sequences) - 1)]
        call_index += 1
        for event in seq:
            yield event

    mock_client.stream = mock_stream
    mock_client.build_request_params = MagicMock(return_value=MagicMock())
    mock_client.messages_to_api_format = MagicMock(return_value=[])
    mock_client.tools_to_api_format = MagicMock(return_value=[])
    # Expose call_index for assertions
    mock_client._get_call_index = lambda: call_index
    return mock_client


@pytest.mark.asyncio
async def test_auto_continue_on_max_output_tokens():
    """First call returns stop_reason='max_output_tokens', second returns 'end_turn'.
    Both text parts should appear in the final response_text."""
    client = _make_api_client([
        [
            StreamEvent(type="text_delta", text="Part one"),
            StreamEvent(type="message_stop", stop_reason="max_output_tokens"),
        ],
        [
            StreamEvent(type="text_delta", text=" Part two"),
            StreamEvent(type="message_stop", stop_reason="end_turn"),
        ],
    ])

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
    assert client._get_call_index() == 2


@pytest.mark.asyncio
async def test_no_continue_on_normal_stop():
    """Single call with 'end_turn' should not trigger continuation."""
    client = _make_api_client([
        [
            StreamEvent(type="text_delta", text="All done"),
            StreamEvent(type="message_stop", stop_reason="end_turn"),
        ],
    ])

    result = await query(
        messages=[UserMessage(content="hello")],
        system="",
        tools=[],
        api_client=client,
        cwd="/tmp",
        max_continuations=3,
    )

    assert result.response_text == "All done"
    assert client._get_call_index() == 1


@pytest.mark.asyncio
async def test_max_continue_limit():
    """All calls return 'max_output_tokens'. With max_continuations=3,
    the loop should stop after 1 initial + 3 continuations = 4 calls total."""
    truncated = [
        StreamEvent(type="text_delta", text="chunk "),
        StreamEvent(type="message_stop", stop_reason="max_output_tokens"),
    ]
    client = _make_api_client([truncated] * 10)  # plenty of sequences

    result = await query(
        messages=[UserMessage(content="hello")],
        system="",
        tools=[],
        api_client=client,
        cwd="/tmp",
        max_continuations=3,
    )

    # 1 initial call + 3 continuations = 4 total calls
    assert client._get_call_index() == 4
    assert "chunk" in result.response_text


# ---------------------------------------------------------------------------
# Reactive compact (prompt_too_long recovery) tests
# ---------------------------------------------------------------------------


def _make_simple_client(stream_fn):
    """Create a mock ClaudeAPIClient with the given stream function."""
    client = MagicMock()
    client.stream = stream_fn
    client.build_request_params = MagicMock(return_value=MagicMock(
        model="claude-opus-4-6", messages=[], system="", tools=[], max_tokens=8096
    ))
    client.messages_to_api_format = MagicMock(return_value=[])
    client.tools_to_api_format = MagicMock(return_value=[])
    return client


class TestIsPromptTooLong:
    """Unit tests for the _is_prompt_too_long helper."""

    def test_prompt_is_too_long_message(self):
        assert _is_prompt_too_long(Exception("prompt is too long")) is True

    def test_prompt_too_long_error_code(self):
        assert _is_prompt_too_long(Exception("prompt_too_long")) is True

    def test_case_insensitive(self):
        assert _is_prompt_too_long(Exception("Prompt Is Too Long")) is True

    def test_unrelated_error(self):
        assert _is_prompt_too_long(Exception("rate limit exceeded")) is False

    def test_embedded_in_larger_message(self):
        assert _is_prompt_too_long(
            Exception("Error: prompt is too long (200k tokens)")
        ) is True


@pytest.mark.asyncio
async def test_reactive_compact_on_prompt_too_long():
    """First API call raises prompt_too_long, reactive_compact runs, second succeeds."""
    call_count = 0

    async def mock_stream(params):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("prompt is too long")
        yield StreamEvent(type="text_delta", text="Recovered!")
        yield StreamEvent(type="message_stop")

    mock_client = _make_simple_client(mock_stream)
    messages = [UserMessage(content="hello")]
    compacted_messages = [UserMessage(content="[summary] compacted")]

    with patch(
        "app.query.reactive_compact",
        new_callable=AsyncMock,
        return_value=(compacted_messages, 100, 50),
    ) as mock_compact:
        result = await query(
            messages=messages,
            system="system prompt",
            tools=[],
            api_client=mock_client,
            cwd="/tmp",
        )

    mock_compact.assert_called_once()
    assert result.response_text == "Recovered!"
    assert call_count == 2


@pytest.mark.asyncio
async def test_no_double_compact():
    """If reactive compact already attempted and API fails again, should re-raise."""
    call_count = 0

    async def mock_stream(params):
        nonlocal call_count
        call_count += 1
        raise Exception("prompt is too long")
        yield  # noqa: unreachable — makes this an async generator

    mock_client = _make_simple_client(mock_stream)
    messages = [UserMessage(content="hello")]
    compacted_messages = [UserMessage(content="[summary] compacted")]

    with patch(
        "app.query.reactive_compact",
        new_callable=AsyncMock,
        return_value=(compacted_messages, 100, 50),
    ) as mock_compact:
        with pytest.raises(Exception, match="prompt is too long"):
            await query(
                messages=messages,
                system="system prompt",
                tools=[],
                api_client=mock_client,
                cwd="/tmp",
            )

    mock_compact.assert_called_once()
    assert call_count == 2


@pytest.mark.asyncio
async def test_non_prompt_error_not_caught():
    """Errors unrelated to prompt_too_long should propagate immediately."""

    async def mock_stream(params):
        raise Exception("rate limit exceeded")
        yield  # noqa: unreachable — makes this an async generator

    mock_client = _make_simple_client(mock_stream)

    with pytest.raises(Exception, match="rate limit exceeded"):
        await query(
            messages=[UserMessage(content="hello")],
            system="system prompt",
            tools=[],
            api_client=mock_client,
            cwd="/tmp",
        )
