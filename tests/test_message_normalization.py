"""Tests for message normalization before API calls."""

from app.message_normalization import normalize_messages_for_api
from app.types.message import (
    AssistantMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


def test_strip_empty_assistant_messages():
    messages = [
        UserMessage(content="hello"),
        AssistantMessage(content=[]),
        UserMessage(content="world"),
    ]
    result = normalize_messages_for_api(messages)
    assert len(result) == 1
    # The two user messages should be merged after the empty assistant is removed
    assert result[0].role.value == "user"
    assert isinstance(result[0].content, list)
    assert len(result[0].content) == 2


def test_merge_consecutive_user_messages():
    messages = [
        UserMessage(content="hello"),
        UserMessage(content=[TextBlock(text="world")]),
        UserMessage(content="!"),
    ]
    result = normalize_messages_for_api(messages)
    assert len(result) == 1
    assert isinstance(result[0].content, list)
    assert len(result[0].content) == 3
    assert result[0].content[0].text == "hello"
    assert result[0].content[1].text == "world"
    assert result[0].content[2].text == "!"


def test_ensure_tool_result_pairing_all_paired():
    """When all tool_use blocks have matching tool_result blocks, nothing changes."""
    messages = [
        UserMessage(content="do something"),
        AssistantMessage(content=[ToolUseBlock(id="tu_1", name="bash", input={"cmd": "ls"})]),
        UserMessage(content=[ToolResultBlock(tool_use_id="tu_1", content="file.txt")]),
    ]
    result = normalize_messages_for_api(messages)
    assert len(result) == 3
    # Verify the tool result is still there unchanged
    assert isinstance(result[2].content, list)
    assert result[2].content[0].tool_use_id == "tu_1"


def test_orphaned_tool_use_gets_synthetic_result():
    """A tool_use without a matching tool_result gets a synthetic error result."""
    messages = [
        UserMessage(content="do something"),
        AssistantMessage(content=[ToolUseBlock(id="tu_orphan", name="bash", input={})]),
    ]
    result = normalize_messages_for_api(messages)
    assert len(result) == 3
    synthetic = result[2]
    assert synthetic.role.value == "user"
    assert isinstance(synthetic.content, list)
    assert len(synthetic.content) == 1
    tr = synthetic.content[0]
    assert isinstance(tr, ToolResultBlock)
    assert tr.tool_use_id == "tu_orphan"
    assert tr.is_error is True


def test_passthrough_normal_conversation():
    """A well-formed conversation passes through unchanged."""
    messages = [
        UserMessage(content="hi"),
        AssistantMessage(content=[TextBlock(text="hello")]),
        UserMessage(content="bye"),
        AssistantMessage(content=[TextBlock(text="goodbye")]),
    ]
    result = normalize_messages_for_api(messages)
    assert len(result) == 4
    assert result[0].content == "hi"
    assert result[1].content[0].text == "hello"
    assert result[2].content == "bye"
    assert result[3].content[0].text == "goodbye"
