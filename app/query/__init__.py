"""Core query function — async generator wrapping QueryRunner.

Matches TypeScript ``query.ts`` top-level ``query()`` function:
an async generator that delegates to ``queryLoop()`` (here ``QueryRunner``),
yielding ``StreamEvent | Message`` and returning a ``Terminal``.

Also provides a convenience ``query()`` function that collects results into
a ``QueryResult`` dataclass for callers that don't need streaming.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, TYPE_CHECKING

from app.abort import AbortController
from app.query.deps import ProductionDeps
from app.query.loop import QueryParams, QueryRunner
from app.query.types import Terminal, TerminalReason
from app.services.api.claude import StreamEvent
from app.types.message import (
    AssistantMessage,
    Message,
    TextBlock,
    ToolUseBlock,
    UserMessage,
)

if TYPE_CHECKING:
    from app.hooks import HookRunner
    from app.services.api.claude import ClaudeAPIClient
    from app.tool import Tool, ToolContext
    from app.tool_executor import ToolExecutor


@dataclass
class QueryResult:
    """Collected result of a complete query turn."""
    response_text: str
    tool_calls: list[dict]
    input_tokens: int = 0
    output_tokens: int = 0
    messages: list[Message] = field(default_factory=list)
    should_exit: bool = False
    terminal: Terminal | None = None


async def query_stream(
    messages: list[Message],
    system: str,
    tools: list[Tool],
    api_client: ClaudeAPIClient,
    cwd: str,
    permission_mode: str = "manual",
    tool_executor: ToolExecutor | None = None,
    tool_context: ToolContext | None = None,
    abort_controller: AbortController | None = None,
    fallback_model: str | None = None,
    max_turns: int | None = None,
    max_output_tokens_override: int | None = None,
    hook_runner: HookRunner | None = None,
    token_budget: int | None = None,
) -> AsyncIterator[StreamEvent | Message]:
    """Async generator that runs the core query loop.

    Yields ``StreamEvent`` and ``Message`` objects as they are produced.
    After iteration ends, the ``QueryRunner.terminal`` attribute holds
    the exit reason.

    This is the primary API for streaming consumers (TUI, SDK).
    """
    from app.tool import ToolContext as _TC

    deps = ProductionDeps(api_client)
    ctx = tool_context or _TC(cwd=cwd, permission_mode=permission_mode)

    params = QueryParams(
        messages=messages,
        system=system,
        tools=tools,
        deps=deps,
        api_client=api_client,
        tool_executor=tool_executor,
        tool_context=ctx,
        abort_controller=abort_controller,
        fallback_model=fallback_model,
        max_turns=max_turns,
        max_output_tokens_override=max_output_tokens_override,
        hook_runner=hook_runner,
        permission_mode=permission_mode,
        token_budget=token_budget,
    )

    runner = QueryRunner(params)
    async for event in runner.run():
        yield event


async def query(
    messages: list[Message],
    system: str,
    tools: list[Tool],
    api_client: ClaudeAPIClient,
    cwd: str,
    permission_mode: str = "manual",
    on_text: Callable[[str], None] | None = None,
    on_tool_use: Callable[[str, dict], None] | None = None,
    tool_executor: ToolExecutor | None = None,
    max_continuations: int = 3,
    token_budget: int | None = None,
) -> QueryResult:
    """Convenience wrapper that collects streaming results into a QueryResult.

    Delegates to ``QueryRunner`` internally. Provides callbacks for text
    and tool-use events for callers that need simple push-style updates
    (e.g., pipe mode).
    """
    from app.tool import ToolContext as _TC

    deps = ProductionDeps(api_client)
    ctx = _TC(cwd=cwd, permission_mode=permission_mode)

    params = QueryParams(
        messages=messages,
        system=system,
        tools=tools,
        deps=deps,
        api_client=api_client,
        tool_executor=tool_executor,
        tool_context=ctx,
        max_turns=max_continuations * 10,  # generous turn limit
        permission_mode=permission_mode,
        token_budget=token_budget,
    )

    runner = QueryRunner(params)
    all_tool_calls: list[dict] = []
    response_parts: list[str] = []
    result_messages: list[Message] = list(messages)

    async for event in runner.run():
        if isinstance(event, StreamEvent):
            if event.type == "text_delta" and on_text:
                on_text(event.text)
            elif event.type == "tool_use" and on_tool_use:
                on_tool_use(event.tool_name, event.tool_input)
            # Collect text
            if event.type == "text_delta":
                response_parts.append(event.text)
        elif isinstance(event, AssistantMessage):
            result_messages.append(event)
            # Extract tool calls
            for block in event.content:
                if isinstance(block, ToolUseBlock):
                    all_tool_calls.append({
                        "tool_name": block.name,
                        "tool_use_id": block.id,
                        "input": block.input,
                    })
            # Collect text from assistant message
            for block in event.content:
                if isinstance(block, TextBlock):
                    if not response_parts or response_parts[-1] != block.text:
                        # Avoid double-counting text already captured via stream
                        pass
        elif isinstance(event, UserMessage):
            result_messages.append(event)

    terminal = runner.terminal
    total_in = terminal.input_tokens if terminal else 0
    total_out = terminal.output_tokens if terminal else 0

    return QueryResult(
        response_text="".join(response_parts),
        tool_calls=all_tool_calls,
        input_tokens=total_in,
        output_tokens=total_out,
        messages=result_messages,
        terminal=terminal,
    )
