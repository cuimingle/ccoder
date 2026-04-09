"""Core query loop — the agentic streaming loop with recovery paths.

Mirrors TypeScript ``query.ts``'s ``queryLoop()`` async generator:

- AsyncGenerator yielding ``StreamEvent | Message``
- Inner attemptWithFallback retry loop for model fallback
- Withheld max_output_tokens pattern (don't yield until recovery exhausts)
- Recovery paths: max_output_tokens escalation (8k→64k), max_output_tokens
  recovery (resume messages), reactive compact, stop hook blocking,
  next turn (tool loop), token budget continuation, auto-compact
- Terminal states: COMPLETED, MAX_TURNS, PROMPT_TOO_LONG, MODEL_ERROR,
  IMAGE_ERROR, BLOCKING_LIMIT, ABORTED_STREAMING, ABORTED_TOOLS,
  STOP_HOOK_PREVENTED, HOOK_STOPPED
- Streaming tool execution during model output
- Model fallback on consecutive 529 errors
- Abort signal handling with graceful drain
- Tool use summary generation (fire-and-forget for next turn)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
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
from app.query.stop_hooks import run_stop_hooks
from app.query.token_budget import BudgetContinue, BudgetTracker, check_token_budget, create_budget_tracker
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
    is_max_output_tokens,
)
from app.services.api.retry import FallbackTriggeredError
from app.streaming_tool_executor import StreamingToolExecutor, ToolUpdate
from app.types.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    Message,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ToolUseSummaryMessage,
    UserMessage,
)

if TYPE_CHECKING:
    from app.abort import AbortSignal
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
    token_budget: int | None = None


class QueryRunner:
    """Runs the core query loop as an AsyncGenerator.

    Mirrors TypeScript ``queryLoop()`` — a while(true) loop that:
    1. Pre-processes messages (compact boundary, budget, microcompact, autocompact)
    2. Streams API response with inner attemptWithFallback retry loop
    3. Starts streaming tool execution during model output
    4. After stream ends: handles recovery paths or terminal states
    5. On tool use: drains remaining tool results, updates state, loops

    Recovery paths (no tool use):
    - Prompt too long → reactive compact → retry
    - Max output tokens → escalation (8k→64k) → retry
    - Max output tokens → resume message → retry (up to 3x)
    - Stop hook blocking → retry with blocking errors
    - Token budget → nudge message → continue

    Usage::

        runner = QueryRunner(params)
        async for event in runner.run():
            handle(event)
        terminal = runner.terminal
    """

    def __init__(self, params: QueryParams) -> None:
        self.params = params
        self.terminal: Terminal | None = None

    async def run(self) -> AsyncIterator[StreamEvent | Message]:
        """Execute the query loop, yielding events and messages."""
        params = self.params

        # -- Mutable cross-iteration state
        state = QueryLoopState(messages=list(params.messages))
        if params.max_output_tokens_override is not None:
            state.max_output_tokens_override = params.max_output_tokens_override

        abort_signal: AbortSignal | None = (
            params.abort_controller.signal if params.abort_controller else None
        )
        auto_compact_tracking = AutoCompactTracking()
        current_model = params.api_client.model

        # Token budget tracker (optional)
        budget_tracker: BudgetTracker | None = None
        if params.token_budget is not None:
            budget_tracker = create_budget_tracker(params.token_budget)

        # ====================================================================
        # Main query loop
        # ====================================================================
        while True:
            # Destructure state at the top of each iteration (matches TS).
            messages = state.messages
            turn_count = state.turn_count
            max_output_tokens_override = state.max_output_tokens_override
            max_output_tokens_recovery_count = state.max_output_tokens_recovery_count
            has_attempted_reactive_compact = state.has_attempted_reactive_compact
            pending_tool_use_summary = state.pending_tool_use_summary
            stop_hook_active = state.stop_hook_active

            yield StreamEvent(type="stream_request_start")

            # ==============================================================
            # Per-iteration setup
            # ==============================================================

            # 1. Get messages after compact boundary
            messages_for_query = get_messages_after_compact_boundary(messages)

            # 2. Apply tool result budget
            messages_for_query = enforce_tool_result_budget(messages_for_query)

            # 3. Apply microcompact
            messages_for_query = params.deps.microcompact(messages_for_query)

            # 4. Apply autocompact if needed
            compact_result = await params.deps.autocompact(
                messages_for_query,
                params.api_client,
                params.system,
                state.total_input_tokens,
                auto_compact_tracking.consecutive_failures,
            )
            if compact_result.was_compacted and compact_result.boundary is not None:
                messages = compact_result.new_messages or []
                messages.insert(0, compact_result.boundary)
                state.total_input_tokens += compact_result.input_tokens
                state.total_output_tokens += compact_result.output_tokens
                auto_compact_tracking = AutoCompactTracking(
                    compacted=True,
                    turn_id=params.deps.uuid(),
                    turn_counter=0,
                    consecutive_failures=0,
                )
                yield compact_result.boundary
                messages_for_query = get_messages_after_compact_boundary(messages)
            elif compact_result.consecutive_failures > 0:
                auto_compact_tracking.consecutive_failures = compact_result.consecutive_failures

            # 5. Check blocking limit (skip if compaction just ran)
            if (
                not compact_result.was_compacted
                and should_compact(state.total_input_tokens)
                and state.total_input_tokens > 0
            ):
                # If over the limit and can't compact, the API will return
                # prompt_too_long — reactive compact handles it below.
                pass

            # ==============================================================
            # API streaming with concurrent tool execution
            # ==============================================================
            executor = StreamingToolExecutor(
                tools=params.tools,
                context=params.tool_context,
                tool_executor=params.tool_executor,
                abort_controller=params.abort_controller,
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
            api_messages = params.api_client.messages_to_api_format(normalized)
            api_tools = await params.api_client.tools_to_api_format(params.tools)

            # Determine max_tokens
            max_tokens = max_output_tokens_override or DEFAULT_MAX_TOKENS

            api_params = params.api_client.build_request_params(
                messages=api_messages,
                system=params.system,
                tools=api_tools,
                max_tokens=max_tokens,
            )

            # ----------------------------------------------------------
            # Inner attemptWithFallback loop (matches TS)
            # ----------------------------------------------------------
            attempt_with_fallback = True

            try:
                while attempt_with_fallback:
                    attempt_with_fallback = False
                    try:
                        async for event in params.deps.call_model(
                            api_params, abort_signal
                        ):
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

                            # Collect tool use — feed to streaming executor immediately
                            if event.type == "tool_use":
                                block = ToolUseBlock(
                                    id=event.tool_use_id,
                                    name=event.tool_name,
                                    input=event.tool_input,
                                )
                                tool_use_blocks.append(block)
                                needs_follow_up = True
                                # Start executing this tool immediately
                                executor.add_tool(block)
                                yield event

                            # Usage tracking
                            if event.type == "usage":
                                state.total_input_tokens += event.input_tokens
                                state.total_output_tokens += event.output_tokens
                                yield event

                            if event.type == "message_start":
                                state.total_input_tokens += event.input_tokens

                            # Poll for completed streaming tool results
                            # during model output
                            for update in executor.get_completed_results():
                                yield update.message
                                tool_results.append(update.message)

                            if event.type == "message_stop":
                                stop_reason = event.stop_reason
                                yield event
                                break

                    except FallbackTriggeredError as e:
                        # Discard pending results from the failed attempt and
                        # create a fresh executor. This prevents orphan
                        # tool_results (with old tool_use_ids) from leaking
                        # into the retry.
                        executor.discard()
                        for msg in yield_missing_tool_result_blocks(
                            [AssistantMessage(content=assistant_content)]
                            if assistant_content
                            else [],
                            f"Discarded: switched to {e.fallback_model}",
                        ):
                            yield msg

                        # Clear all arrays for retry
                        assistant_content.clear()
                        tool_use_blocks.clear()
                        tool_results.clear()
                        response_text_parts.clear()
                        needs_follow_up = False

                        current_model = e.fallback_model
                        params.api_client.model = e.fallback_model

                        # Recreate executor for the retry
                        executor = StreamingToolExecutor(
                            tools=params.tools,
                            context=params.tool_context,
                            tool_executor=params.tool_executor,
                            abort_controller=params.abort_controller,
                        )

                        yield StreamEvent(
                            type="text_delta",
                            text=(
                                f"\n\n[Switched to {e.fallback_model} "
                                f"due to high demand]\n\n"
                            ),
                        )
                        attempt_with_fallback = True
                        continue

            except Exception as e:
                classified = classify_error(e)

                if classified.type == APIErrorType.PROMPT_TOO_LONG:
                    # Withhold the error — recovery path below will handle it
                    withheld_error = e

                elif classified.type == APIErrorType.IMAGE_SIZE_ERROR:
                    self.terminal = Terminal(
                        reason=TerminalReason.IMAGE_ERROR,
                        input_tokens=state.total_input_tokens,
                        output_tokens=state.total_output_tokens,
                    )
                    yield StreamEvent(type="error", text=classified.message)
                    return

                else:
                    # Generally callModel should not throw errors but instead
                    # yield them as synthetic assistant messages. However if it
                    # does throw, we may have already emitted a tool_use block
                    # but will stop before emitting the tool_result.
                    for msg in yield_missing_tool_result_blocks(
                        [AssistantMessage(content=assistant_content)]
                        if assistant_content
                        else [],
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

            # ==============================================================
            # Build assistant message for this turn
            # ==============================================================
            response_text = "".join(response_text_parts)
            if response_text:
                assistant_content.append(TextBlock(text=response_text))
            for block in tool_use_blocks:
                assistant_content.append(block)

            assistant_messages: list[AssistantMessage] = []

            # Determine if this is a withheld max_output_tokens response.
            # Mirrors TS isWithheldMaxOutputTokens — the error was produced by
            # the model stopping at the output limit. We hold it back from
            # consumers until we know whether the recovery loop can continue.
            # Yielding early leaks an intermediate error to SDK callers that
            # terminate the session on any ``error`` field.
            is_withheld_max_tokens = (
                is_max_output_tokens(stop_reason) and not needs_follow_up
            )

            if assistant_content:
                asst = AssistantMessage(
                    content=assistant_content,
                    stop_reason=stop_reason,
                    is_api_error=withheld_error is not None,
                )
                assistant_messages.append(asst)
                # Only yield if NOT withheld for recovery
                if not is_withheld_max_tokens:
                    yield asst

            # ==============================================================
            # Check abort after streaming
            # ==============================================================
            if abort_signal and abort_signal.aborted:
                # Consume remaining results — executor generates synthetic
                # tool_results for aborted tools since it checks the abort
                # signal in executeTool().
                async for update in executor.get_remaining_results():
                    yield update.message

                self.terminal = Terminal(
                    reason=TerminalReason.ABORTED_STREAMING,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                )
                return

            # ==============================================================
            # Yield pending tool use summary from previous turn
            # ==============================================================
            # The summary was generated during the previous turn's tool
            # execution (~1s via fast model) and resolved while this turn's
            # model was streaming (5-30s).
            if pending_tool_use_summary is not None:
                try:
                    summary = await pending_tool_use_summary
                    if summary is not None:
                        yield summary
                except Exception:
                    pass

            # ==============================================================
            # No tool use path (needsFollowUp = false)
            # ==============================================================
            if not needs_follow_up:
                last_message = (
                    assistant_messages[-1] if assistant_messages else None
                )

                # --- Recovery: prompt_too_long (withheld error) ---
                # The streaming loop withheld the error. Try reactive compact
                # (full summary). Single-shot — if a retry still 413's, the
                # error surfaces.
                if withheld_error is not None and is_prompt_too_long(
                    withheld_error
                ):
                    if not has_attempted_reactive_compact:
                        try:
                            compacted, comp_in, comp_out = await reactive_compact(
                                messages,
                                params.api_client,
                                params.system,
                            )
                            state.total_input_tokens += comp_in
                            state.total_output_tokens += comp_out
                            # New state for retry
                            state.messages = compacted
                            state.has_attempted_reactive_compact = True
                            state.max_output_tokens_override = None
                            state.pending_tool_use_summary = None
                            state.stop_hook_active = False
                            state.transition = Continue(
                                reason=ContinueReason.REACTIVE_COMPACT_RETRY
                            )
                            continue
                        except Exception:
                            logger.exception("Reactive compact failed")

                    # No recovery — surface the error and exit. Do NOT fall
                    # through to stop hooks: the model never produced a valid
                    # response, so hooks have nothing to evaluate.
                    self.terminal = Terminal(
                        reason=TerminalReason.PROMPT_TOO_LONG,
                        input_tokens=state.total_input_tokens,
                        output_tokens=state.total_output_tokens,
                    )
                    yield StreamEvent(type="error", text="Prompt is too long")
                    return

                # --- Recovery: max_output_tokens escalation (8k → 64k) ---
                # If we used the capped 8k default and hit the limit, retry
                # the SAME request at 64k — no meta message, no multi-turn
                # dance. Fires once per turn (guarded by the override check),
                # then falls through to multi-turn recovery if 64k also hits.
                if (
                    is_withheld_max_tokens
                    and max_output_tokens_override is None
                ):
                    logger.info(
                        "Escalating max_tokens to %d", ESCALATED_MAX_TOKENS
                    )
                    state.messages = list(messages_for_query)
                    state.max_output_tokens_override = ESCALATED_MAX_TOKENS
                    state.pending_tool_use_summary = None
                    state.stop_hook_active = False
                    state.transition = Continue(
                        reason=ContinueReason.MAX_OUTPUT_TOKENS_ESCALATE
                    )
                    continue

                # --- Recovery: max_output_tokens with resume message ---
                if (
                    is_withheld_max_tokens
                    and max_output_tokens_recovery_count
                    < MAX_OUTPUT_TOKENS_RECOVERY_LIMIT
                ):
                    recovery_msg = UserMessage(
                        content=MAX_OUTPUT_TOKENS_RECOVERY_MESSAGE
                    )
                    state.messages = [
                        *messages_for_query,
                        *assistant_messages,
                        recovery_msg,
                    ]
                    state.max_output_tokens_recovery_count = (
                        max_output_tokens_recovery_count + 1
                    )
                    state.has_attempted_reactive_compact = (
                        has_attempted_reactive_compact
                    )
                    state.max_output_tokens_override = None
                    state.pending_tool_use_summary = None
                    state.stop_hook_active = False
                    state.transition = Continue(
                        reason=ContinueReason.MAX_OUTPUT_TOKENS_RECOVERY,
                        attempt=max_output_tokens_recovery_count + 1,
                    )
                    logger.info(
                        "Max output tokens recovery attempt %d/%d",
                        max_output_tokens_recovery_count + 1,
                        MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
                    )
                    continue

                # Recovery exhausted — surface the withheld message now.
                if is_withheld_max_tokens and last_message is not None:
                    yield last_message

                # --- Skip stop hooks when the last message is an API error
                # (rate limit, prompt-too-long, auth failure, etc.). The model
                # never produced a real response — hooks evaluating it create
                # a death spiral: error → hook blocking → retry → error → …
                if last_message is not None and last_message.is_api_error:
                    self.terminal = Terminal(
                        reason=TerminalReason.COMPLETED,
                        input_tokens=state.total_input_tokens,
                        output_tokens=state.total_output_tokens,
                    )
                    return

                # --- Stop hooks ---
                if params.hook_runner is not None:
                    tool_names = [b.name for b in tool_use_blocks]
                    hook_result = await run_stop_hooks(
                        messages_for_query,
                        params.hook_runner,
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
                        blocking_msgs = [
                            UserMessage(content=err)
                            for err in hook_result.blocking_errors
                        ]
                        state.messages = [
                            *messages_for_query,
                            *assistant_messages,
                            *blocking_msgs,
                        ]
                        state.max_output_tokens_recovery_count = 0
                        # Preserve has_attempted_reactive_compact — if compact
                        # already ran and couldn't recover from prompt-too-long,
                        # retrying after a stop-hook blocking error will produce
                        # the same result. Resetting to false here caused an
                        # infinite loop: compact → still too long → error →
                        # stop hook blocking → compact → …
                        state.has_attempted_reactive_compact = (
                            has_attempted_reactive_compact
                        )
                        state.max_output_tokens_override = None
                        state.pending_tool_use_summary = None
                        state.stop_hook_active = True
                        state.transition = Continue(
                            reason=ContinueReason.STOP_HOOK_BLOCKING
                        )
                        continue

                # --- Token budget check ---
                if budget_tracker is not None:
                    decision = check_token_budget(
                        budget_tracker,
                        state.total_output_tokens,
                    )
                    if isinstance(decision, BudgetContinue):
                        logger.debug(
                            "Token budget continuation #%d: %d%% "
                            "(%d / %d)",
                            decision.pct,
                            decision.turn_tokens,
                            decision.budget,
                            budget_tracker.continuation_count,
                        )
                        nudge_msg = UserMessage(
                            content=decision.nudge_message
                        )
                        state.messages = [
                            *messages_for_query,
                            *assistant_messages,
                            nudge_msg,
                        ]
                        state.max_output_tokens_recovery_count = 0
                        state.has_attempted_reactive_compact = False
                        state.max_output_tokens_override = None
                        state.pending_tool_use_summary = None
                        state.stop_hook_active = False
                        state.transition = Continue(
                            reason=ContinueReason.TOKEN_BUDGET_CONTINUATION
                        )
                        continue

                # --- Normal completion ---
                self.terminal = Terminal(
                    reason=TerminalReason.COMPLETED,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                )
                return

            # ==============================================================
            # Tool execution path (needsFollowUp = true)
            # ==============================================================
            should_prevent_continuation = False

            # Get remaining results from streaming executor (tools that
            # started during model output but haven't finished yet)
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

            # If a hook indicated to prevent continuation, stop here
            if should_prevent_continuation:
                self.terminal = Terminal(
                    reason=TerminalReason.HOOK_STOPPED,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                )
                return

            # Track turns since last compaction
            if auto_compact_tracking.compacted:
                auto_compact_tracking.turn_counter += 1

            # Generate tool use summary after tool batch completes — passed
            # to next iteration for deferred yielding. The summary generation
            # runs concurrently with the next API call (it resolves in ~1s
            # via a fast model while the main model streams for 5-30s).
            next_pending_summary = _start_tool_use_summary(
                tool_use_blocks,
                tool_results,
                assistant_messages,
                abort_signal,
            )

            # Check max turns
            next_turn = turn_count + 1
            if (
                params.max_turns is not None
                and next_turn > params.max_turns
            ):
                self.terminal = Terminal(
                    reason=TerminalReason.MAX_TURNS,
                    input_tokens=state.total_input_tokens,
                    output_tokens=state.total_output_tokens,
                    extra={"turn_count": next_turn},
                )
                return

            # Update state for next iteration
            state.messages = [
                *messages_for_query,
                *assistant_messages,
                *tool_results,
            ]
            state.turn_count = next_turn
            state.max_output_tokens_recovery_count = 0
            state.has_attempted_reactive_compact = False
            state.max_output_tokens_override = None
            state.pending_tool_use_summary = next_pending_summary
            state.stop_hook_active = False
            state.transition = Continue(reason=ContinueReason.NEXT_TURN)


# ---------------------------------------------------------------------------
# Tool use summary generation
# ---------------------------------------------------------------------------


def _start_tool_use_summary(
    tool_use_blocks: list[ToolUseBlock],
    tool_results: list[Message],
    assistant_messages: list[AssistantMessage],
    abort_signal: AbortSignal | None,
) -> asyncio.Task[ToolUseSummaryMessage | None] | None:
    """Fire off a tool use summary generation task (for next turn yield).

    Mirrors TypeScript ``generateToolUseSummary`` — runs via a fast model
    (e.g. Haiku) concurrently with the next API call. The result is awaited
    at the start of the following iteration.

    Returns an asyncio.Task wrapping the summary, or None if summary
    generation is not applicable.
    """
    if not tool_use_blocks:
        return None

    if abort_signal and abort_signal.aborted:
        return None

    # TODO: Implement actual summary generation via fast model (Haiku).
    # The plumbing is in place — when implemented, this function should:
    # 1. Extract last assistant text for context
    # 2. Collect tool name/input/output for each tool_use block
    # 3. Call a fast model to produce a short summary
    # 4. Return asyncio.create_task(generate(...)) wrapping a
    #    ToolUseSummaryMessage
    #
    # For now, return None — no summary is generated.
    return None
