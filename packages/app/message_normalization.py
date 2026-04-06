"""Normalize message lists before sending to Claude API.

Three normalization passes:
1. Strip empty assistant messages
2. Merge consecutive user messages
3. Ensure every ToolUseBlock has a matching ToolResultBlock
"""

from __future__ import annotations

from app.types.message import (
    AssistantMessage,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


def normalize_messages_for_api(messages: list[Message]) -> list[Message]:
    """Apply all normalization passes and return a clean message list."""
    result = _strip_empty_assistants(messages)
    result = _merge_consecutive_users(result)
    result = _ensure_tool_result_pairing(result)
    return result


def _strip_empty_assistants(messages: list[Message]) -> list[Message]:
    """Remove AssistantMessage entries with empty content lists."""
    return [
        m
        for m in messages
        if not (isinstance(m, AssistantMessage) and len(m.content) == 0)
    ]


def _merge_consecutive_users(messages: list[Message]) -> list[Message]:
    """Merge consecutive UserMessage entries into a single UserMessage with list content."""
    if not messages:
        return []

    result: list[Message] = []
    for msg in messages:
        if (
            isinstance(msg, UserMessage)
            and result
            and isinstance(result[-1], UserMessage)
        ):
            # Merge into previous user message
            prev = result[-1]
            prev_blocks = _to_content_blocks(prev.content)
            cur_blocks = _to_content_blocks(msg.content)
            result[-1] = UserMessage(content=prev_blocks + cur_blocks)
        else:
            result.append(msg)
    return result


def _ensure_tool_result_pairing(messages: list[Message]) -> list[Message]:
    """Add synthetic error ToolResultBlock for any ToolUseBlock without a matching result."""
    # Collect all tool_use IDs
    tool_use_ids: set[str] = set()
    for msg in messages:
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    tool_use_ids.add(block.id)

    # Collect all tool_result IDs
    tool_result_ids: set[str] = set()
    for msg in messages:
        if isinstance(msg, UserMessage) and isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    tool_result_ids.add(block.tool_use_id)

    orphans = tool_use_ids - tool_result_ids
    if not orphans:
        return messages

    # Add a synthetic user message with error results for each orphan
    synthetic_blocks = [
        ToolResultBlock(
            tool_use_id=tid,
            content="Tool execution was interrupted before producing a result.",
            is_error=True,
        )
        for tid in sorted(orphans)
    ]
    return messages + [UserMessage(content=synthetic_blocks)]


def _to_content_blocks(content: str | list) -> list:
    """Convert string content to a list containing a single TextBlock."""
    if isinstance(content, str):
        return [TextBlock(text=content)]
    return list(content)


def yield_missing_tool_result_blocks(
    assistant_messages: list[AssistantMessage],
    error_message: str = "Tool execution was interrupted before producing a result.",
) -> list[UserMessage]:
    """Generate synthetic tool_result UserMessages for each tool_use without a result.

    Used in abort/error paths to ensure every tool_use has a matching tool_result.
    """
    result_messages = []
    for msg in assistant_messages:
        blocks = []
        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                blocks.append(
                    ToolResultBlock(
                        tool_use_id=block.id,
                        content=error_message,
                        is_error=True,
                    )
                )
        if blocks:
            result_messages.append(UserMessage(content=blocks))
    return result_messages
