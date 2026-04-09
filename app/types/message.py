"""Message type hierarchy for Claude API communication."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class TextBlock:
    text: str
    type: str = field(default="text", init=False)


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = field(default="tool_use", init=False)


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str | list[dict]
    is_error: bool = False
    type: str = field(default="tool_result", init=False)


@dataclass
class ThinkingBlock:
    """Extended thinking content from the model."""
    thinking: str
    signature: str = ""
    type: str = field(default="thinking", init=False)


ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock]


@dataclass
class UserMessage:
    content: str | list[ContentBlock]
    role: MessageRole = field(default=MessageRole.USER, init=False)


@dataclass
class AssistantMessage:
    content: list[ContentBlock]
    role: MessageRole = field(default=MessageRole.ASSISTANT, init=False)
    is_api_error: bool = False
    stop_reason: str = ""


@dataclass
class SystemMessage:
    content: str
    role: MessageRole = field(default=MessageRole.SYSTEM, init=False)


@dataclass
class CompactBoundaryMessage:
    """Marker inserted after compaction; messages before this are discarded."""
    summary: str
    role: MessageRole = field(default=MessageRole.SYSTEM, init=False)
    compact_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolUseSummaryMessage:
    """Async summary of tool use from previous turn."""
    summary: str
    preceding_tool_ids: list[str] = field(default_factory=list)


Message = Union[
    UserMessage,
    AssistantMessage,
    SystemMessage,
    CompactBoundaryMessage,
]


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------

@dataclass
class MessageUsage:
    """Token usage counters for a single API response."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


def accumulate_usage(total: MessageUsage, delta: MessageUsage) -> MessageUsage:
    """Sum two usage counters."""
    return MessageUsage(
        input_tokens=total.input_tokens + delta.input_tokens,
        output_tokens=total.output_tokens + delta.output_tokens,
        cache_creation_input_tokens=total.cache_creation_input_tokens + delta.cache_creation_input_tokens,
        cache_read_input_tokens=total.cache_read_input_tokens + delta.cache_read_input_tokens,
    )


# ---------------------------------------------------------------------------
# SDK message — unified yield type for QueryEngine.submit_message()
# ---------------------------------------------------------------------------

@dataclass
class SDKMessage:
    """Unified message type yielded by QueryEngine.submit_message().

    Mirrors TypeScript ``SDKMessage`` — all yields from the engine carry
    one of these so SDK / TUI consumers have a single type to switch on.
    """
    type: str  # system_init, user, assistant, tool_result, stream_event,
    #             compact_boundary, tool_use_summary, result
    subtype: str = ""  # for result: success | error_max_turns | error_max_budget_usd | error_during_execution
    message: Message | None = None
    event: Any = None  # StreamEvent, when type == "stream_event"
    init_data: dict[str, Any] | None = None  # for system_init
    result_data: dict[str, Any] | None = None  # for result
    usage: MessageUsage | None = None
    session_id: str = ""
    is_error: bool = False
    # result fields
    duration_ms: int = 0
    num_turns: int = 0
    result_text: str = ""
    stop_reason: str | None = None
    total_cost_usd: float = 0.0
    errors: list[str] | None = None
    permission_denials: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Permission denial record
# ---------------------------------------------------------------------------

@dataclass
class PermissionDenial:
    """A record of a denied tool-use permission, for SDK reporting."""
    tool_name: str
    tool_use_id: str
    tool_input: dict[str, Any] = field(default_factory=dict)
