"""Core query loop — the agentic streaming loop with recovery paths.

Replaces the original ``query()`` function with a full ``QueryRunner``
class that mirrors the TypeScript ``query.ts`` control flow:

- AsyncGenerator yielding ``StreamEvent | Message``
- 7 recovery/continuation paths
- 10 terminal states
- Streaming tool execution during model output
- Model fallback on consecutive 529 errors
- Abort signal handling with graceful drain
- Auto-compact and reactive compact integration
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, TYPE_CHECKING

from app.abort import AbortController
from app.compaction import (
    get_messages_after_compact_boundary,
    reactive_compact,
    should_compact,
)
from app.message_normalization import (
    normalize_messages_for_api,
    yield_missing_tool_result_blocks,
)
from app.query.stop_hooks import run_stop_hooks, StopHookResult
from app.query.tool_result_budget import enforce_tool_result_budget
from app.query.types import (
    AutoCompactTracking,
    Continue,
    ContinueReason,
    DEFAULT_MAX_TOKENS,
    ESCALATED_MAX_TOKENS,
    MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
    MAX_OUTPUT_TOKENS_RECOVERY_MESSAGE,
    QueryLoopState,
    Terminal,
    TerminalReason,
)
from app.services.api.claude import APIRequestParams, StreamEvent
from app.services.api.errors import (
    APIErrorType,
    classify_error,
    is_prompt_too_long,
)
from app.services.api.retry import FallbackTriggeredError
from app.streaming_tool_executor import StreamingToolExecutor
from app.types.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    Message,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    UserMessage,
)

if TYPE_CHECKING:
    from app.hooks import HookRunner
    from app.query.deps import QueryDeps
    from app.services.api.claude import ClaudeAPIClient
    from app.tool import Tool, ToolContext
    from app.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)


@dataclass
class QueryParams:
    """Parameters for the query loop."""
    messages: list[Message]
    system: str
    tools: list[Tool]
    deps: QueryDeps
    api_client: ClaudeAPIClient
    tool_executor: ToolExecutor | None = None
    tool_context: ToolContext | None = None
    abort_controller: AbortController | None = None
    fallback_model: str | None = None
    max_turns: int | None = None
    max_output_tokens_override: int | None = None
    hook_runner: HookRunner | None = None
    permission_mode: str = "manual"


class QueryRunner:
    """Runs the core query loop as an AsyncGenerator.

    Usage::

        runner = QueryRunner(params)
        async for event in runner.run():
            handle(event)
        terminal = runner.terminal

    The ``terminal`` attribute holds the reason the loop exited.
    """

    def __init__(self, params: QueryParams) -> None:
        self.params = params
        self.terminal: Terminal | None = None

    async def run(self) -> AsyncIterator[StreamEvent | Message]:
        """Execute the query loop, yielding events and messages."""
        state = QueryLoopState(messages=list(self.params.messages))
        if self.params.max_output_tokens_override is not None:
            state.max_output_tokens_override = self.params.max_output_tokens_override

        abort_signal = (
            self.params.abort_controller.signal
            if self.params.abort_controller
            else None
        )
        auto_compact_tracking = AutoCompactTracking()
        current_model = self.params.api_client.model

        while True:
            # ============================================================
            # Per-iteration setup
            # ============================================================
            yield StreamEvent(type="stream_request_start")

            # 1. Get messages after compact boundary
            messages_for_query = get_messages_after_compact_boundary(state.messages)

            # 2. Apply tool result budget
            messages_for_query = enforce_tool_result_budget(messages_for_query)

            # 3. Apply microcompact
            messages_for_query = self.params.deps.microcompact(messages_for_query)

            # 4. Apply autocompact if needed
            compact_result = await self.params.deps.autocompact(
                messages_for_query,
                self.params.api_client,
                self.params.system,
                state.total_input_tokens,
                auto_compact_tracking.consecutive_failures,
            )
            if compact_result.was_compacted and compact_result.boundary is not None:
                state.messages = compact_result.new_messages or []
                state.messages.insert(0, compact_result.boundary)
                state.total_input_tokens += compact_result.input_tokens
                state.total_output_tokens += compact_result.output_tokens
                auto_compact_tracking.consecutive_failures = 0
                yield compact_result.boundary
                messages_for_query = get_messages_after_compact_boundary(state.messages)
            else:
                auto_compact_tracking.consecutive_failures = compact_result.consecutive_failures

            # 5. Check blocking limit (skip if compaction just ran)
            if (
                not compact_result.was_compacted
                and should_compact(state.total_input_tokens)
                and state.total_input_tokens > 0
            ):
                # If we're over the limit and can't compact, exit
                pass  # We don't hard-block here; the API will return prompt_too_long

            # ============================================================
            # API streaming
            # ============================================================
            executor = StreamingToolExecutor(
                tools=self.params.tools,
                context=self.params.tool_context,
                tool_executor=self.params.tool_executor,
                abort_controller=self.params.abort_controller,
            )

            assistant_content: list = []
            tool_use_blocks: list[ToolUseBlock] = []
            needs_follow_up = False
            tool_results: list[Message] = []
            stop_reason = ""
            withheld_error: Exception | None = None
            response_text_parts: list[str] = []

            # Normalize messages for API
            normalized = normalize_messages_for_api(messages_for_query)
            api_messages = self.params.api_client.messages_to_api_format(normalized)
            api_tools = self.params.api_client.tools_to_api_format(self.params.tools)

            # Determine max_tokens
            max_tokens = state.max_output_tokens_override or DEFAULT_MAX_TOKENS

            params = self.params.api_client.build_request_params(
                messages=api_messages,
                system=self.params.system,
                tools=api_tools,
                max_tokens=max_tokens,
            )

            try:
                stream = await self.params.deps.call_model(params, abort_signal)
                async for event in stream:
                    if abort_signal and abort_signal.aborted:
                        break

                    # Yield most events to the consumer
                    if event.type in (
                        "text_delta",
                        "thinking_delta",
                        "content_block_start",
                        "content_block_stop",
                        "message_start",
                    ):
                        yield event

                    # Collect text
                    if event.type == "text_delta":
                        response_text_parts.append(event.text)

                    # Collect tool use
                    if event.type == "tool_use":
                        block = ToolUseBlock(
                            id=event.tool_use_id,
                            name=event.tool_name,
                            input=event.tool_input,
                        )
                        tool_use_blocks.append(block)
                        needs_follow_up = True
                        # Feed to streaming executor
                        executor.add_tool(block)
                        yield event

                    # Usage tracking
                    if event.type == "usage":
                        state.total_input_tokens += event.input_tokens
                        state.total_output_tokens += event.output_tokens
                        yield event

                    if event.type == "message_start":
                        state.total_input_tokens += event.input_tokens

                    # Yield completed streaming tool results
                    for update in executor.get_completed_results():
                        yield update.message
                        tool_results.append(update.message)

                    if event.type == "message_stop":
                        stop_reason = event.stop_reason
                        yield event
                        break

            except FallbackTriggeredError as e:
                # Tombstone orphaned messages, retry with fallback model
                executor.discard()
                # Yield missing tool results for any in-progress tool_use
                for msg in yield_missing_tool_result_blocks(
                    [AssistantMessage(content=assistant_content)] if assistant_content else [],
                    f"Discarded: switched to {e.fallback_model}",
                ):
                    yield msg
                    tool_results.append(msg)

                current_model = e.fallback_model
                self.params.api_client.model = e.fallback_model
                yield StreamEvent(
                    type="text_delta",
                    text=f"\n\n[Switched to {e.fallback_model} due to high demand]\n\n",
                )
                # Continue the loop with the fallback model
                state.transition = Continue(reason=ContinueReason.NEXT_TURN)
                continue

            except Exception as e:
                classified = classify_error(e)

                if classified.type == APIErrorType.PROMPT_TOO_LONG:
                    withheld_error = e
                elif classified.type == APIErrorType.IMAGE_SIZE_ERROR:
                    self.terminal = Terminal(
                        reason=TerminalReason.IMAGE_ERROR,
                        input_tokens=state.total_input_tokens,
                        output_tokens=state.total_output_tokens,
                    )
                    yield StreamEvent(
                        type="error", text=classified.message
                    )
                    return
                else:
                    # Yield missing tool results
                    for msg in yield_missing_tool_result_blocks(
                        [AssistantMessage(content=assistant_content)] if assistant_content else [],
                        str(e),
                    ):
                        yield msg

                    self.terminal = Terminal(
                        reason=TerminalReason.MODEL_ERROR,
                        input_tokens=state.total_input_tokens,
                        output_tokens=state.total_output_tokens,
                        extra={"error": str(e)},
                    )
                    yield StreamEvent(type="error", text=classified.message)
                    return

            # Build assistant message for this turn
            response_text = "".join(response_text_parts)
            if response_text:
                assistant_content.append(TextBlock(text=response_text))
            for block in tool_use_blocks:
                assistant_content.append(block)

            assistant_messages: list[AssistantMessage] = []
            if assistant_content:
                asst = AssistantMessage(content=assistant_content, stop_reason=stop_reason)
                assistant_messages.append(asst)
                yield asst

            # ============================================================
            # Check abort after streaming
            # ============================================================
            if abort_signal and abort_signal.aborted:
                # Consume remaining from executor
                async for update in executor.get_remaining_results():
                    yield update.message

                self.terminal = Terminal(
                    reason=TerminalReason.ABORTED_STREAMING,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                )
                return

            # ============================================================
            # No tool use path (needsFollowUp = false)
            # ============================================================
            if not needs_follow_up:
                # --- Recovery: prompt_too_long ---
                if withheld_error is not None and is_prompt_too_long(withheld_error):
                    if not state.has_attempted_reactive_compact:
                        state.has_attempted_reactive_compact = True
                        try:
                            compacted, comp_in, comp_out = await reactive_compact(
                                state.messages,
                                self.params.api_client,
                                self.params.system,
                            )
                            state.messages = compacted
                            state.total_input_tokens += comp_in
                            state.total_output_tokens += comp_out
                            state.transition = Continue(
                                reason=ContinueReason.REACTIVE_COMPACT_RETRY
                            )
                            continue
                        except Exception:
                            logger.exception("Reactive compact failed")

                    self.terminal = Terminal(
                        reason=TerminalReason.PROMPT_TOO_LONG,
                        input_tokens=state.total_input_tokens,
                        output_tokens=state.total_output_tokens,
                    )
                    yield StreamEvent(type="error", text="Prompt is too long")
                    return

                # --- Recovery: max_output_tokens escalation (8k -> 64k) ---
                if (
                    stop_reason in ("max_tokens", "max_output_tokens")
                    and state.max_output_tokens_override is None
                ):
                    state.max_output_tokens_override = ESCALATED_MAX_TOKENS
                    # Keep assistant messages in conversation
                    state.messages.extend(assistant_messages)
                    state.transition = Continue(
                        reason=ContinueReason.MAX_OUTPUT_TOKENS_ESCALATE
                    )
                    logger.info(
                        "Escalating max_tokens to %d", ESCALATED_MAX_TOKENS
                    )
                    continue

                # --- Recovery: max_output_tokens with resume message ---
                if (
                    stop_reason in ("max_tokens", "max_output_tokens")
                    and state.max_output_tokens_recovery_count
                    < MAX_OUTPUT_TOKENS_RECOVERY_LIMIT
                ):
                    recovery_msg = UserMessage(
                        content=MAX_OUTPUT_TOKENS_RECOVERY_MESSAGE
                    )
                    state.messages.extend([*assistant_messages, recovery_msg])
                    state.max_output_tokens_recovery_count += 1
                    state.transition = Continue(
                        reason=ContinueReason.MAX_OUTPUT_TOKENS_RECOVERY,
                        attempt=state.max_output_tokens_recovery_count,
                    )
                    logger.info(
                        "Max output tokens recovery attempt %d/%d",
                        state.max_output_tokens_recovery_count,
                        MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
                    )
                    continue

                # --- Stop hooks ---
                if self.params.hook_runner is not None:
                    tool_names = [b.name for b in tool_use_blocks]
                    hook_result = await run_stop_hooks(
                        state.messages,
                        self.params.hook_runner,
                        tool_names,
                    )
                    if hook_result.prevent_continuation:
                        self.terminal = Terminal(
                            reason=TerminalReason.STOP_HOOK_PREVENTED,
                            input_tokens=state.total_input_tokens,
                            output_tokens=state.total_output_tokens,
                        )
                        return
                    if hook_result.blocking_errors:
                        for err in hook_result.blocking_errors:
                            state.messages.append(UserMessage(content=err))
                        state.messages.extend(assistant_messages)
                        state.transition = Continue(
                            reason=ContinueReason.STOP_HOOK_BLOCKING
                        )
                        continue

                # --- Normal completion ---
                self.terminal = Terminal(
                    reason=TerminalReason.COMPLETED,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                )
                return

            # ============================================================
            # Tool execution path (needsFollowUp = true)
            # ============================================================

            # Get remaining results from streaming executor
            async for update in executor.get_remaining_results():
                yield update.message
                tool_results.append(update.message)

            # Check abort during tool execution
            if abort_signal and abort_signal.aborted:
                self.terminal = Terminal(
                    reason=TerminalReason.ABORTED_TOOLS,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                )
                return

            # Check max turns
            next_turn = state.turn_count + 1
            if self.params.max_turns is not None and next_turn > self.params.max_turns:
                self.terminal = Terminal(
                    reason=TerminalReason.MAX_TURNS,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                    extra={"turn_count": next_turn},
                )
                return

            # Update state for next iteration
            state.messages.extend([*assistant_messages, *tool_results])
            state.turn_count = next_turn
            state.max_output_tokens_recovery_count = 0
            state.has_attempted_reactive_compact = False
            state.transition = Continue(reason=ContinueReason.NEXT_TURN)
