"""QueryEngine — session orchestrator owning the query lifecycle.

Mirrors TypeScript ``QueryEngine`` class: one instance per conversation,
each ``submit_message()`` call starts a new turn.  State (messages, usage,
file cache, permission denials) persists across turns.

Provides three APIs:
- ``submit_message()`` — async generator yielding ``SDKMessage`` (primary)
- ``run_turn()`` — collected-result convenience wrapper (legacy)
- ``ask()`` — module-level one-shot convenience function
"""
from __future__ import annotations

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, AsyncIterator, Callable

from app.abort import AbortController
from app.command_registry import CommandRegistry
from app.commands import build_default_registry, parse_command
from app.compaction import (
    compact_conversation,
    micro_compact_messages,
    should_compact,
)
from app.context import build_system_prompt
from app.hooks import HookRunner
from app.permissions import PermissionChecker
from app.query import query, query_stream, QueryResult
from app.query.deps import ProductionDeps
from app.query.loop import QueryParams, QueryRunner
from app.query.types import Terminal, TerminalReason
from app.services.api.claude import ClaudeAPIClient, StreamEvent
from app.settings import Settings, load_settings
from app.tool import Tool, ToolContext
from app.tool_executor import PermissionCallback, ToolExecutor
from app.tool_registry import get_tools
from app.types.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    Message,
    MessageUsage,
    PermissionDenial,
    SDKMessage,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    accumulate_usage,
)
from app.types.permissions import PermissionMode

logger = logging.getLogger(__name__)

# Pricing per million tokens (Claude Opus-class, matches cost.py)
INPUT_PRICE_PER_M = 15.0
OUTPUT_PRICE_PER_M = 75.0


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts."""
    return (
        input_tokens * INPUT_PRICE_PER_M / 1_000_000
        + output_tokens * OUTPUT_PRICE_PER_M / 1_000_000
    )


# ---------------------------------------------------------------------------
# QueryEngineConfig — typed config bag matching TS QueryEngineConfig
# ---------------------------------------------------------------------------

@dataclass
class QueryEngineConfig:
    """Configuration for a QueryEngine instance."""
    cwd: str
    api_key: str | None = None
    base_url: str | None = None
    model: str = "claude-opus-4-6"
    permission_mode: str = "manual"
    permission_callback: PermissionCallback | None = None
    initial_messages: list[Message] | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    custom_system_prompt: str | None = None
    append_system_prompt: str | None = None
    fallback_model: str | None = None
    verbose: bool = False


class QueryEngine:
    """Manages conversation state across multiple turns.

    One QueryEngine per conversation.  Each ``submit_message()`` call
    starts a new turn within the same conversation.  State (messages,
    file cache, usage, permission denials) persists across turns.

    Corresponds to the TypeScript ``QueryEngine`` class.
    """

    def __init__(
        self,
        config: QueryEngineConfig | None = None,
        # Legacy positional kwargs — kept for backward compatibility
        cwd: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "claude-opus-4-6",
        permission_mode: str = "manual",
        permission_callback: PermissionCallback | None = None,
    ):
        # Accept either config object or legacy kwargs
        if config is not None:
            c = config
        else:
            c = QueryEngineConfig(
                cwd=cwd or ".",
                api_key=api_key,
                base_url=base_url,
                model=model,
                permission_mode=permission_mode,
                permission_callback=permission_callback,
            )

        self.cwd = c.cwd
        self.permission_mode = c.permission_mode
        self._config = c

        # Conversation state
        self._mutable_messages: list[Message] = list(c.initial_messages or [])
        self.turn_count: int = 0
        self._total_usage = MessageUsage()
        self._permission_denials: list[PermissionDenial] = []
        self._last_stop_reason: str | None = None

        # API client
        self._api_client = ClaudeAPIClient(
            api_key=c.api_key, base_url=c.base_url, model=c.model,
        )

        # Tools, permissions, hooks
        self._tools: list[Tool] = get_tools()
        settings = load_settings(c.cwd)
        mode = PermissionMode(c.permission_mode)
        self._permission_checker = PermissionChecker(settings, mode)
        self._hook_runner = HookRunner(settings.hooks)
        self._tool_executor = ToolExecutor(
            self._permission_checker, self._hook_runner, c.permission_callback,
        )
        self._command_registry = build_default_registry()

        # Session / abort
        self._session_id: str = str(uuid.uuid4())
        self._abort_controller: AbortController | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def messages(self) -> list[Message]:
        return self._mutable_messages

    @messages.setter
    def messages(self, value: list[Message]) -> None:
        self._mutable_messages = value

    @property
    def command_registry(self) -> CommandRegistry:
        return self._command_registry

    @property
    def model(self) -> str:
        return self._api_client.model

    @model.setter
    def model(self, value: str) -> None:
        self._api_client.model = value

    @property
    def total_input_tokens(self) -> int:
        return self._total_usage.input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_usage.output_tokens

    @property
    def total_cost_usd(self) -> float:
        return _estimate_cost(
            self._total_usage.input_tokens,
            self._total_usage.output_tokens,
        )

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def abort_controller(self) -> AbortController | None:
        return self._abort_controller

    # ------------------------------------------------------------------
    # Abort
    # ------------------------------------------------------------------

    def create_abort_controller(self) -> AbortController:
        self._abort_controller = AbortController()
        return self._abort_controller

    def abort(self, reason: str = "aborted") -> None:
        if self._abort_controller:
            self._abort_controller.abort(reason)

    def interrupt(self) -> None:
        """Interrupt the current turn (alias used by TS QueryEngine)."""
        self.abort()

    # ------------------------------------------------------------------
    # Accessors (match TS getMessages / getSessionId / setModel)
    # ------------------------------------------------------------------

    def get_messages(self) -> list[Message]:
        return list(self._mutable_messages)

    def get_session_id(self) -> str:
        return self._session_id

    def set_model(self, model: str) -> None:
        self._api_client.model = model

    # ------------------------------------------------------------------
    # Streaming API — async generator yielding SDKMessage
    # ------------------------------------------------------------------

    async def submit_message(
        self,
        user_input: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[SDKMessage, None]:
        """Submit a user message and yield SDKMessage objects.

        This is the primary API for TUI/SDK consumers.  Mirrors the
        TypeScript ``submitMessage()`` method: yields ``SDKMessage``
        objects covering system_init, stream events, assistant/user
        messages, compact boundaries, and a final ``result`` message.

        Handles slash commands inline — command results are yielded
        as ``SDKMessage(type="result")`` with the text payload.
        """
        start_time = time.monotonic()
        self._permission_denials.clear()

        # ----------------------------------------------------------
        # 1. Yield system init
        # ----------------------------------------------------------
        system = build_system_prompt(cwd=self.cwd)
        yield SDKMessage(
            type="system_init",
            session_id=self._session_id,
            init_data={
                "model": self._api_client.model,
                "cwd": self.cwd,
                "permission_mode": self.permission_mode,
                "tools": [t.name for t in self._tools if t.is_enabled()],
            },
        )

        # ----------------------------------------------------------
        # 2. Handle slash commands
        # ----------------------------------------------------------
        cmd = parse_command(user_input)
        if cmd is not None:
            for msg in await self._handle_slash_command_async(cmd, start_time):
                yield msg
            return

        # ----------------------------------------------------------
        # 3. Normal message — delegate to QueryRunner
        # ----------------------------------------------------------
        self._mutable_messages.append(UserMessage(content=user_input))
        abort_controller = self.create_abort_controller()

        deps = ProductionDeps(self._api_client)
        tool_context = ToolContext(
            cwd=self.cwd,
            permission_mode=self.permission_mode,
            session_id=self._session_id,
            abort_signal=abort_controller.signal,
        )

        params = QueryParams(
            messages=self._mutable_messages,
            system=system,
            tools=self._tools,
            deps=deps,
            api_client=self._api_client,
            tool_executor=self._tool_executor,
            tool_context=tool_context,
            abort_controller=abort_controller,
            hook_runner=self._hook_runner,
            permission_mode=self.permission_mode,
            fallback_model=self._config.fallback_model,
            max_turns=self._config.max_turns,
        )

        runner = QueryRunner(params)

        # Per-message usage (reset on each message_start)
        current_msg_usage = MessageUsage()
        turn_count = 1

        async for event in runner.run():
            # ---- Collect messages into mutable store ----
            if isinstance(event, AssistantMessage):
                self._mutable_messages.append(event)
                # Capture stop_reason if already set (synthetic messages)
                if event.stop_reason:
                    self._last_stop_reason = event.stop_reason
                yield SDKMessage(type="assistant", message=event, session_id=self._session_id)

            elif isinstance(event, UserMessage):
                self._mutable_messages.append(event)
                turn_count += 1
                yield SDKMessage(type="user", message=event, session_id=self._session_id)

            elif isinstance(event, CompactBoundaryMessage):
                self._mutable_messages.append(event)
                # Release pre-compaction messages for GC
                boundary_idx = len(self._mutable_messages) - 1
                if boundary_idx > 0:
                    del self._mutable_messages[:boundary_idx]
                yield SDKMessage(
                    type="compact_boundary",
                    message=event,
                    session_id=self._session_id,
                )

            elif isinstance(event, StreamEvent):
                # --- Usage tracking from stream events ---
                if event.type == "message_start":
                    current_msg_usage = MessageUsage()
                    current_msg_usage = MessageUsage(
                        input_tokens=event.input_tokens,
                    )

                if event.type == "usage":
                    current_msg_usage = MessageUsage(
                        input_tokens=current_msg_usage.input_tokens,
                        output_tokens=current_msg_usage.output_tokens + event.output_tokens,
                    )

                if event.type == "message_stop":
                    # Accumulate into total
                    self._total_usage = accumulate_usage(
                        self._total_usage, current_msg_usage,
                    )
                    # Capture stop_reason from message_stop
                    if event.stop_reason:
                        self._last_stop_reason = event.stop_reason

                # Yield stream events
                yield SDKMessage(
                    type="stream_event",
                    event=event,
                    session_id=self._session_id,
                )

                # --- Max budget check ---
                if (
                    self._config.max_budget_usd is not None
                    and self.total_cost_usd >= self._config.max_budget_usd
                ):
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    yield self._make_result(
                        subtype="error_max_budget_usd",
                        is_error=True,
                        duration_ms=duration_ms,
                        num_turns=turn_count,
                        errors=[f"Reached maximum budget (${self._config.max_budget_usd})"],
                    )
                    return

            else:
                # Other message types (e.g. tool results as UserMessage) —
                # already handled above via isinstance checks
                pass

        # ----------------------------------------------------------
        # 4. Post-loop: update session state from terminal
        # ----------------------------------------------------------
        terminal = runner.terminal
        if terminal:
            self._total_usage = accumulate_usage(
                self._total_usage,
                MessageUsage(
                    input_tokens=terminal.input_tokens,
                    output_tokens=terminal.output_tokens,
                ),
            )

        # Update conversation messages from runner
        self._mutable_messages = list(params.messages)
        self.turn_count += 1

        # ----------------------------------------------------------
        # 5. Auto-compact if needed
        # ----------------------------------------------------------
        if should_compact(self._total_usage.input_tokens):
            await self._auto_compact()

        # ----------------------------------------------------------
        # 6. Yield final result
        # ----------------------------------------------------------
        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Validate result: check if the last message is a successful completion
        result_msg = self._find_last_result_message()
        is_successful = self._is_result_successful(result_msg, terminal)

        if not is_successful:
            # Error during execution
            errors = self._collect_terminal_errors(terminal)
            yield self._make_result(
                subtype="error_during_execution",
                is_error=True,
                duration_ms=duration_ms,
                num_turns=turn_count,
                errors=errors,
            )
            return

        # Check terminal for max_turns
        if terminal and terminal.reason == TerminalReason.MAX_TURNS:
            max_turns = terminal.extra.get("turn_count", turn_count)
            yield self._make_result(
                subtype="error_max_turns",
                is_error=True,
                duration_ms=duration_ms,
                num_turns=turn_count,
                errors=[f"Reached maximum number of turns ({self._config.max_turns})"],
            )
            return

        # Extract text result
        text_result = self._extract_text_result(result_msg)

        yield self._make_result(
            subtype="success",
            is_error=False,
            duration_ms=duration_ms,
            num_turns=turn_count,
            result_text=text_result,
        )

    # ------------------------------------------------------------------
    # Collected-result API (legacy/convenience)
    # ------------------------------------------------------------------

    async def run_turn(
        self,
        user_input: str,
        on_text: Callable[[str], None] | None = None,
        on_tool_use: Callable[[str, dict], None] | None = None,
    ) -> QueryResult:
        """Run a single conversation turn (legacy convenience API).

        For new code, prefer ``submit_message()`` which yields ``SDKMessage``
        objects with full lifecycle information.
        """
        # Handle slash commands
        cmd = parse_command(user_input)
        if cmd is not None:
            command_name, args = cmd
            if command_name == "compact":
                return await self._handle_compact()
            if command_name == "clear":
                self.clear()
                return QueryResult(response_text="Session cleared.", tool_calls=[])

            context = self._build_command_context()
            result = await self._command_registry.execute(command_name, args, context)
            qr = QueryResult(response_text=result.text, tool_calls=[])
            qr.should_exit = result.should_exit
            return qr

        self._mutable_messages.append(UserMessage(content=user_input))
        system = build_system_prompt(cwd=self.cwd)

        result = await query(
            messages=self._mutable_messages,
            system=system,
            tools=self._tools,
            api_client=self._api_client,
            cwd=self.cwd,
            permission_mode=self.permission_mode,
            on_text=on_text,
            on_tool_use=on_tool_use,
            tool_executor=self._tool_executor,
        )

        # Update session state
        self._mutable_messages = result.messages
        self.turn_count += 1
        self._total_usage = accumulate_usage(
            self._total_usage,
            MessageUsage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            ),
        )

        # Auto-compact if needed
        if should_compact(self._total_usage.input_tokens):
            await self._auto_compact()

        return result

    # ------------------------------------------------------------------
    # Compaction
    # ------------------------------------------------------------------

    async def _handle_compact(self) -> QueryResult:
        summary_text = await self.compact()
        return QueryResult(
            response_text=f"Conversation compacted.\n\n{summary_text}",
            tool_calls=[],
        )

    async def compact(self) -> str:
        """Compact the conversation and return the summary text."""
        system = build_system_prompt(cwd=self.cwd)
        new_messages, in_tokens, out_tokens = await compact_conversation(
            self._mutable_messages, self._api_client, system,
        )
        self._mutable_messages = new_messages
        self._total_usage = accumulate_usage(
            self._total_usage,
            MessageUsage(input_tokens=in_tokens, output_tokens=out_tokens),
        )

        if new_messages and isinstance(new_messages[0].content, str):
            return new_messages[0].content
        return "Conversation compacted."

    async def _auto_compact(self) -> None:
        """Auto-compact: micro-compact first, then full compact if still needed."""
        self._mutable_messages = micro_compact_messages(self._mutable_messages)
        if should_compact(self._total_usage.input_tokens):
            await self.compact()

    def clear(self) -> None:
        """Reset the session state."""
        self._mutable_messages = []
        self.turn_count = 0
        self._total_usage = MessageUsage()
        self._permission_denials = []
        self._last_stop_reason = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _handle_slash_command_async(
        self,
        cmd: tuple[str, str],
        start_time: float,
    ) -> list[SDKMessage]:
        """Handle a slash command, returning SDKMessage list."""
        command_name, args = cmd
        duration_ms = int((time.monotonic() - start_time) * 1000)

        if command_name == "compact":
            result = await self._handle_compact()
            return [self._make_result(
                subtype="success",
                is_error=False,
                duration_ms=duration_ms,
                num_turns=0,
                result_text=result.response_text,
            )]

        if command_name == "clear":
            self.clear()
            return [self._make_result(
                subtype="success",
                is_error=False,
                duration_ms=duration_ms,
                num_turns=0,
                result_text="Session cleared.",
            )]

        context = self._build_command_context()
        result = await self._command_registry.execute(command_name, args, context)
        return [self._make_result(
            subtype="success",
            is_error=False,
            duration_ms=duration_ms,
            num_turns=0,
            result_text=result.text,
        )]

    def _build_command_context(self) -> dict[str, Any]:
        return {
            "engine": self,
            "registry": self._command_registry,
            "total_input_tokens": self._total_usage.input_tokens,
            "total_output_tokens": self._total_usage.output_tokens,
            "turn_count": self.turn_count,
            "cwd": self.cwd,
            "app_state": getattr(self, "_app_state", None),
        }

    def _make_result(
        self,
        *,
        subtype: str,
        is_error: bool,
        duration_ms: int,
        num_turns: int,
        result_text: str = "",
        errors: list[str] | None = None,
    ) -> SDKMessage:
        """Build a ``result`` SDKMessage."""
        return SDKMessage(
            type="result",
            subtype=subtype,
            session_id=self._session_id,
            is_error=is_error,
            duration_ms=duration_ms,
            num_turns=num_turns,
            result_text=result_text,
            stop_reason=self._last_stop_reason,
            total_cost_usd=self.total_cost_usd,
            usage=MessageUsage(
                input_tokens=self._total_usage.input_tokens,
                output_tokens=self._total_usage.output_tokens,
            ),
            errors=errors,
            permission_denials=[
                {
                    "tool_name": d.tool_name,
                    "tool_use_id": d.tool_use_id,
                    "tool_input": d.tool_input,
                }
                for d in self._permission_denials
            ] if self._permission_denials else None,
        )

    def _find_last_result_message(self) -> Message | None:
        """Find the last assistant or user message (for result extraction)."""
        for msg in reversed(self._mutable_messages):
            if isinstance(msg, (AssistantMessage, UserMessage)):
                return msg
        return None

    @staticmethod
    def _is_result_successful(
        result: Message | None,
        terminal: Terminal | None,
    ) -> bool:
        """Check if the query result indicates success.

        Mirrors TS ``isResultSuccessful()`` — the result must be an
        assistant message with text/thinking content, or a user message
        with tool_result blocks.  Also accepts ``end_turn`` stop_reason.
        """
        if result is None:
            return False

        if terminal and terminal.reason in (
            TerminalReason.MODEL_ERROR,
            TerminalReason.IMAGE_ERROR,
            TerminalReason.PROMPT_TOO_LONG,
            TerminalReason.ABORTED_STREAMING,
            TerminalReason.ABORTED_TOOLS,
        ):
            return False

        if isinstance(result, AssistantMessage):
            if not result.content:
                return False
            last_block = result.content[-1]
            return hasattr(last_block, "type") and last_block.type in ("text", "thinking")

        if isinstance(result, UserMessage):
            # User message with tool_result blocks is valid terminal state
            if isinstance(result.content, list):
                from app.types.message import ToolResultBlock
                return any(
                    isinstance(b, ToolResultBlock) for b in result.content
                )

        return False

    @staticmethod
    def _extract_text_result(msg: Message | None) -> str:
        """Extract text content from the last assistant message."""
        if msg is None:
            return ""
        if isinstance(msg, AssistantMessage) and msg.content:
            last = msg.content[-1]
            if hasattr(last, "type") and last.type == "text" and hasattr(last, "text"):
                return last.text
        return ""

    @staticmethod
    def _collect_terminal_errors(terminal: Terminal | None) -> list[str]:
        """Collect error descriptions from a terminal state."""
        if terminal is None:
            return ["Unknown error: no terminal state"]

        errors = [
            f"[ede_diagnostic] reason={terminal.reason.value}",
        ]
        if "error" in terminal.extra:
            errors.append(str(terminal.extra["error"]))
        return errors


# ---------------------------------------------------------------------------
# ask() — one-shot convenience wrapper (matches TS export)
# ---------------------------------------------------------------------------

async def ask(
    *,
    prompt: str,
    cwd: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "claude-opus-4-6",
    permission_mode: str = "auto",
    permission_callback: PermissionCallback | None = None,
    initial_messages: list[Message] | None = None,
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    custom_system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    fallback_model: str | None = None,
    verbose: bool = False,
) -> AsyncGenerator[SDKMessage, None]:
    """Send a single prompt and yield SDKMessage responses.

    Convenience wrapper around ``QueryEngine`` for one-shot / headless
    usage.  Mirrors the TypeScript ``ask()`` export.
    """
    config = QueryEngineConfig(
        cwd=cwd,
        api_key=api_key,
        base_url=base_url,
        model=model,
        permission_mode=permission_mode,
        permission_callback=permission_callback,
        initial_messages=initial_messages,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        custom_system_prompt=custom_system_prompt,
        append_system_prompt=append_system_prompt,
        fallback_model=fallback_model,
        verbose=verbose,
    )

    engine = QueryEngine(config=config)
    async for msg in engine.submit_message(prompt):
        yield msg
