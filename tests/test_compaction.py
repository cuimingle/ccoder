"""Tests for compaction system."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.compaction import (
    COMPACT_THRESHOLD,
    CONTEXT_WINDOW,
    MAX_TOOL_RESULT_CHARS,
    TRUNCATED_KEEP_CHARS,
    compact_conversation,
    micro_compact_message,
    micro_compact_messages,
    should_compact,
)
from app.types.message import (
    AssistantMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from app.services.api.claude import StreamEvent


class TestShouldCompact:
    def test_below_threshold(self):
        assert should_compact(100_000) is False

    def test_at_threshold(self):
        tokens = int(CONTEXT_WINDOW * COMPACT_THRESHOLD) + 1
        assert should_compact(tokens) is True

    def test_above_threshold(self):
        assert should_compact(190_000) is True

    def test_zero_tokens(self):
        assert should_compact(0) is False


class TestMicroCompact:
    def test_short_content_unchanged(self):
        msg = UserMessage(
            content=[
                ToolResultBlock(tool_use_id="1", content="short result", is_error=False)
            ]
        )
        result = micro_compact_message(msg)
        assert result is msg  # unchanged, same object

    def test_long_content_truncated(self):
        long_content = "x" * (MAX_TOOL_RESULT_CHARS + 1000)
        msg = UserMessage(
            content=[
                ToolResultBlock(tool_use_id="1", content=long_content, is_error=False)
            ]
        )
        result = micro_compact_message(msg)
        assert result is not msg
        block = result.content[0]
        assert isinstance(block, ToolResultBlock)
        assert "[... truncated ...]" in block.content
        assert len(block.content) < len(long_content)
        # Starts with the beginning of original content
        assert block.content.startswith("x" * TRUNCATED_KEEP_CHARS)

    def test_assistant_message_unchanged(self):
        msg = AssistantMessage(content=[TextBlock(text="hello")])
        result = micro_compact_message(msg)
        assert result is msg

    def test_string_content_unchanged(self):
        msg = UserMessage(content="plain text")
        result = micro_compact_message(msg)
        assert result is msg

    def test_mixed_blocks_only_truncates_long(self):
        short_block = ToolResultBlock(tool_use_id="1", content="short", is_error=False)
        long_block = ToolResultBlock(
            tool_use_id="2", content="y" * (MAX_TOOL_RESULT_CHARS + 100), is_error=False
        )
        msg = UserMessage(content=[short_block, long_block])
        result = micro_compact_message(msg)
        assert result.content[0].content == "short"
        assert "[... truncated ...]" in result.content[1].content

    def test_micro_compact_messages_batch(self):
        msgs = [
            UserMessage(content="hello"),
            UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id="1",
                        content="z" * (MAX_TOOL_RESULT_CHARS + 100),
                        is_error=False,
                    )
                ]
            ),
        ]
        result = micro_compact_messages(msgs)
        assert len(result) == 2
        assert result[0] is msgs[0]  # unchanged
        assert result[1] is not msgs[1]  # truncated


class TestCompactConversation:
    @pytest.fixture
    def mock_api_client(self):
        client = MagicMock()

        async def mock_stream(params):
            yield StreamEvent(type="text_delta", text="Summary of conversation.")
            yield StreamEvent(type="usage", input_tokens=500, output_tokens=100)
            yield StreamEvent(type="message_stop")

        client.stream = mock_stream
        client.build_request_params = MagicMock(return_value=MagicMock())
        return client

    @pytest.mark.asyncio
    async def test_compact_replaces_history(self, mock_api_client):
        messages = [
            UserMessage(content="first question"),
            AssistantMessage(content=[TextBlock(text="first answer")]),
            UserMessage(content="second question"),
        ]
        new_msgs, in_tokens, out_tokens = await compact_conversation(
            messages, mock_api_client, "system prompt"
        )
        assert len(new_msgs) == 2
        # First is summary
        assert "[Previous conversation summary]" in new_msgs[0].content
        assert "Summary of conversation." in new_msgs[0].content
        # Second is last user message
        assert new_msgs[1].content == "second question"
        assert in_tokens == 500
        assert out_tokens == 100

    @pytest.mark.asyncio
    async def test_compact_too_few_messages(self, mock_api_client):
        messages = [UserMessage(content="only one")]
        new_msgs, in_t, out_t = await compact_conversation(
            messages, mock_api_client, "sys"
        )
        assert new_msgs is messages
        assert in_t == 0

    @pytest.mark.asyncio
    async def test_compact_preserves_last_user_message(self, mock_api_client):
        messages = [
            UserMessage(content="setup"),
            AssistantMessage(content=[TextBlock(text="ok")]),
            UserMessage(content="the important question"),
        ]
        new_msgs, _, _ = await compact_conversation(
            messages, mock_api_client, "sys"
        )
        assert new_msgs[-1].content == "the important question"

    @pytest.mark.asyncio
    async def test_compact_no_user_messages_to_summarize(self, mock_api_client):
        """If all messages are the last user message, nothing to summarize."""
        messages = [UserMessage(content="only")]
        new_msgs, _, _ = await compact_conversation(messages, mock_api_client, "sys")
        assert new_msgs is messages
