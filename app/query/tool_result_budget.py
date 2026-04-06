"""Tool result budget enforcement.

Truncates oversized tool results before sending to the API, matching
the TypeScript ``applyToolResultBudget`` behavior.
"""
from __future__ import annotations

from app.types.message import (
    Message,
    ToolResultBlock,
    UserMessage,
)

# Per-turn budget for total tool result content
MAX_TOOL_RESULT_BUDGET = 800_000  # characters
TRUNCATION_KEEP = 2_000  # chars to keep at head and tail


def enforce_tool_result_budget(
    messages: list[Message],
    budget_chars: int = MAX_TOOL_RESULT_BUDGET,
) -> list[Message]:
    """Truncate tool result content that exceeds the per-turn budget.

    Walks messages in reverse (most recent first) and truncates the
    largest tool results until total content fits within budget.
    """
    # First pass: measure total
    total = 0
    for msg in messages:
        if isinstance(msg, UserMessage) and isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, ToolResultBlock) and isinstance(block.content, str):
                    total += len(block.content)

    if total <= budget_chars:
        return messages

    # Need to truncate — process in reverse to preserve recent results
    excess = total - budget_chars
    result = list(messages)

    for i in range(len(result) - 1, -1, -1):
        if excess <= 0:
            break
        msg = result[i]
        if not isinstance(msg, UserMessage) or isinstance(msg.content, str):
            continue

        new_blocks = []
        changed = False
        for block in msg.content:
            if (
                excess > 0
                and isinstance(block, ToolResultBlock)
                and isinstance(block.content, str)
                and len(block.content) > TRUNCATION_KEEP * 2 + 100
            ):
                original_len = len(block.content)
                truncated = (
                    block.content[:TRUNCATION_KEEP]
                    + f"\n\n[... {original_len - TRUNCATION_KEEP * 2} chars truncated ...]\n\n"
                    + block.content[-TRUNCATION_KEEP:]
                )
                excess -= original_len - len(truncated)
                new_blocks.append(
                    ToolResultBlock(
                        tool_use_id=block.tool_use_id,
                        content=truncated,
                        is_error=block.is_error,
                    )
                )
                changed = True
            else:
                new_blocks.append(block)

        if changed:
            result[i] = UserMessage(content=new_blocks)

    return result
