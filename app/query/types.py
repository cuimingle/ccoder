"""State machine types for the query loop.

Defines Terminal (exit reasons), Continue (loop continuation reasons),
QueryLoopState (mutable per-iteration state), and related constants.

Matches TypeScript ``query.ts`` state types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio

    from app.types.message import Message, ToolUseSummaryMessage


# ---------------------------------------------------------------------------
# Terminal — query loop exit
# ---------------------------------------------------------------------------

class TerminalReason(str, Enum):
    BLOCKING_LIMIT = "blocking_limit"
    MODEL_ERROR = "model_error"
    IMAGE_ERROR = "image_error"
    ABORTED_STREAMING = "aborted_streaming"
    ABORTED_TOOLS = "aborted_tools"
    PROMPT_TOO_LONG = "prompt_too_long"
    STOP_HOOK_PREVENTED = "stop_hook_prevented"
    HOOK_STOPPED = "hook_stopped"
    COMPLETED = "completed"
    MAX_TURNS = "max_turns"


@dataclass(frozen=True)
class Terminal:
    """Immutable record of why the query loop exited."""
    reason: TerminalReason
    input_tokens: int = 0
    output_tokens: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Continue — loop continuation reasons
# ---------------------------------------------------------------------------

class ContinueReason(str, Enum):
    NEXT_TURN = "next_turn"
    MAX_OUTPUT_TOKENS_ESCALATE = "max_output_tokens_escalate"
    MAX_OUTPUT_TOKENS_RECOVERY = "max_output_tokens_recovery"
    REACTIVE_COMPACT_RETRY = "reactive_compact_retry"
    STOP_HOOK_BLOCKING = "stop_hook_blocking"
    TOKEN_BUDGET_CONTINUATION = "token_budget_continuation"


@dataclass(frozen=True)
class Continue:
    """Immutable record of why the query loop continued."""
    reason: ContinueReason
    attempt: int = 0


# ---------------------------------------------------------------------------
# Mutable state across query loop iterations
# ---------------------------------------------------------------------------

@dataclass
class QueryLoopState:
    """Mutable state carried across query-loop iterations.

    Matches TypeScript ``State`` — the loop body destructures this at the
    top of each iteration, and continue sites write the fields back.
    """
    messages: list[Message]
    turn_count: int = 1  # starts at 1, matching TS
    max_output_tokens_recovery_count: int = 0
    has_attempted_reactive_compact: bool = False
    max_output_tokens_override: int | None = None
    pending_tool_use_summary: asyncio.Task[ToolUseSummaryMessage | None] | None = None
    stop_hook_active: bool = False
    transition: Continue | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0


# ---------------------------------------------------------------------------
# Auto-compact tracking
# ---------------------------------------------------------------------------

@dataclass
class AutoCompactTracking:
    """Tracks auto-compaction state across iterations.

    Matches TypeScript ``AutoCompactTrackingState``.
    """
    compacted: bool = False
    turn_id: str = ""
    turn_counter: int = 0
    consecutive_failures: int = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3
ESCALATED_MAX_TOKENS = 64_000
DEFAULT_MAX_TOKENS = 8_096
CONTEXT_WINDOW = 200_000

# Recovery message injected when max_output_tokens is hit
MAX_OUTPUT_TOKENS_RECOVERY_MESSAGE = (
    "Output token limit hit. Resume directly \u2014 no apology, no recap of what you were doing. "
    "Pick up mid-thought if that is where the cut happened. "
    "Break remaining work into smaller pieces."
)
