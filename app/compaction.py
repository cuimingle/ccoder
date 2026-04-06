"""Session compaction — auto-compact, micro-compact, and API summarization."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from app.types.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    Message,
    TextBlock,
    ToolResultBlock,
    UserMessage,
)
from app.services.api.claude import ClaudeAPIClient

logger = logging.getLogger(__name__)

# Claude model context window
CONTEXT_WINDOW = 200_000
COMPACT_THRESHOLD = 0.90

# Micro-compact limits
MAX_TOOL_RESULT_CHARS = 10_000
TRUNCATED_KEEP_CHARS = 2_000

COMPACT_SYSTEM_PROMPT = (
    "You are a conversation summarizer. Summarize the conversation below concisely, "
    "preserving: key decisions made, code changes performed, files modified, current task state, "
    "and any important context needed to continue the work. Be factual and specific."
)


def should_compact(total_input_tokens: int) -> bool:
    """Check if conversation should be compacted based on token usage."""
    return total_input_tokens > CONTEXT_WINDOW * COMPACT_THRESHOLD


def micro_compact_message(message: Message) -> Message:
    """
    Truncate overly long tool result content in a message.
    Keeps first and last TRUNCATED_KEEP_CHARS chars with truncation marker.
    """
    if not isinstance(message, UserMessage):
        return message

    content = message.content
    if isinstance(content, str):
        return message

    changed = False
    new_blocks = []
    for block in content:
        if isinstance(block, ToolResultBlock) and isinstance(block.content, str):
            if len(block.content) > MAX_TOOL_RESULT_CHARS:
                truncated = (
                    block.content[:TRUNCATED_KEEP_CHARS]
                    + "\n\n[... truncated ...]\n\n"
                    + block.content[-TRUNCATED_KEEP_CHARS:]
                )
                new_blocks.append(
                    ToolResultBlock(
                        tool_use_id=block.tool_use_id,
                        content=truncated,
                        is_error=block.is_error,
                    )
                )
                changed = True
                continue
        new_blocks.append(block)

    if not changed:
        return message
    return UserMessage(content=new_blocks)


def micro_compact_messages(messages: list[Message]) -> list[Message]:
    """Apply micro-compaction to all messages in the conversation."""
    return [micro_compact_message(m) for m in messages]


def _messages_to_summary_text(messages: list[Message]) -> str:
    """Convert messages to a plain-text representation for summarization."""
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            if isinstance(msg.content, str):
                parts.append(f"User: {msg.content}")
            else:
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        content_str = block.content if isinstance(block.content, str) else str(block.content)
                        status = "error" if block.is_error else "ok"
                        parts.append(f"Tool result ({status}): {content_str[:500]}")
        elif isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    parts.append(f"Assistant: {block.text}")
    return "\n".join(parts)


async def compact_conversation(
    messages: list[Message],
    api_client: ClaudeAPIClient,
    system: str,
) -> tuple[list[Message], int, int]:
    """
    Summarize the conversation via an API call.

    Returns (new_messages, input_tokens_used, output_tokens_used).
    The new messages list contains a summary user message followed by
    the last user message from the original conversation.
    """
    if len(messages) < 2:
        return messages, 0, 0

    # Keep the last user message separate
    last_user_msg = None
    messages_to_summarize = messages
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], UserMessage):
            last_user_msg = messages[i]
            messages_to_summarize = messages[:i]
            break

    if not messages_to_summarize:
        return messages, 0, 0

    # Build summary request
    conversation_text = _messages_to_summary_text(messages_to_summarize)
    summary_request = [
        {
            "role": "user",
            "content": f"Summarize this conversation:\n\n{conversation_text}",
        }
    ]

    params = api_client.build_request_params(
        messages=summary_request,
        system=COMPACT_SYSTEM_PROMPT,
        tools=[],
    )

    # Collect the summary
    summary_parts: list[str] = []
    input_tokens = 0
    output_tokens = 0

    async for event in api_client.stream(params):
        if event.type == "text_delta":
            summary_parts.append(event.text)
        elif event.type == "usage":
            input_tokens += event.input_tokens
            output_tokens += event.output_tokens
        elif event.type == "message_stop":
            break

    summary_text = "".join(summary_parts)

    # Build new message list with summary
    new_messages: list[Message] = [
        UserMessage(content=f"[Previous conversation summary]:\n{summary_text}"),
    ]
    if last_user_msg is not None:
        new_messages.append(last_user_msg)

    return new_messages, input_tokens, output_tokens


async def reactive_compact(
    messages: list[Message],
    api_client: ClaudeAPIClient,
    system: str,
) -> tuple[list[Message], int, int]:
    """Emergency compaction triggered by prompt_too_long error."""
    compacted = micro_compact_messages(messages)
    return await compact_conversation(compacted, api_client, system)


# ---------------------------------------------------------------------------
# Compact boundary helpers
# ---------------------------------------------------------------------------

MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3


def get_messages_after_compact_boundary(messages: list[Message]) -> list[Message]:
    """Return messages after the last CompactBoundaryMessage.

    If no boundary exists, returns the full list.
    """
    last_boundary_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, CompactBoundaryMessage):
            last_boundary_idx = i

    if last_boundary_idx == -1:
        return messages
    return messages[last_boundary_idx:]


def build_post_compact_messages(
    summary: str,
    metadata: dict | None = None,
) -> CompactBoundaryMessage:
    """Create a CompactBoundaryMessage after successful compaction."""
    return CompactBoundaryMessage(
        summary=summary,
        compact_metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Auto-compact with circuit breaker
# ---------------------------------------------------------------------------

@dataclass
class AutoCompactResult:
    """Result of an auto-compact attempt."""
    was_compacted: bool
    new_messages: list[Message] | None = None
    boundary: CompactBoundaryMessage | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    consecutive_failures: int = 0


async def auto_compact_if_needed(
    messages: list[Message],
    api_client: ClaudeAPIClient,
    system: str,
    total_input_tokens: int,
    consecutive_failures: int = 0,
) -> AutoCompactResult:
    """Proactive compaction with circuit breaker.

    Returns AutoCompactResult indicating whether compaction occurred.
    Stops trying after MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES failures.
    """
    if not should_compact(total_input_tokens):
        return AutoCompactResult(was_compacted=False, consecutive_failures=consecutive_failures)

    if consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        logger.warning(
            "Auto-compact skipped: %d consecutive failures (max %d)",
            consecutive_failures,
            MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES,
        )
        return AutoCompactResult(was_compacted=False, consecutive_failures=consecutive_failures)

    try:
        micro_compacted = micro_compact_messages(messages)
        new_messages, in_tok, out_tok = await compact_conversation(
            micro_compacted, api_client, system
        )

        summary = ""
        if new_messages and isinstance(new_messages[0].content, str):
            summary = new_messages[0].content

        boundary = build_post_compact_messages(summary)

        return AutoCompactResult(
            was_compacted=True,
            new_messages=new_messages,
            boundary=boundary,
            input_tokens=in_tok,
            output_tokens=out_tok,
            consecutive_failures=0,
        )
    except Exception:
        logger.exception("Auto-compact failed")
        return AutoCompactResult(
            was_compacted=False,
            consecutive_failures=consecutive_failures + 1,
        )
