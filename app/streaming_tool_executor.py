"""StreamingToolExecutor — concurrent tool execution with ordering guarantees.

Matches TypeScript ``StreamingToolExecutor`` behavior:

- Tools are added via ``add_tool()`` as they arrive during model streaming.
- ``get_completed_results()`` is a synchronous poll that yields results for
  tools that have already finished, preserving queue order.
- ``get_remaining_results()`` is an async generator that waits for all
  remaining tools to finish.
- ``discard()`` cancels all pending/in-progress tool tasks (used on fallback).

Tools marked ``is_concurrent_safe = True`` may overlap execution.
Tools marked ``is_concurrent_safe = False`` run exclusively.
Queue order is always respected for yielding results.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, TYPE_CHECKING

from app.tool import Tool, ToolContext, ToolResult, find_tool_by_name
from app.types.message import ToolResultBlock, ToolUseBlock, UserMessage, Message

if TYPE_CHECKING:
    from app.abort import AbortController
    from app.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)


class ToolStatus(Enum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    YIELDED = "yielded"
    DISCARDED = "discarded"


@dataclass
class TrackedTool:
    block: ToolUseBlock
    tool: Tool | None
    status: ToolStatus = ToolStatus.QUEUED
    is_concurrent_safe: bool = True
    result: ToolResult | None = None
    task: asyncio.Task | None = None  # type: ignore[type-arg]
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class ToolUpdate:
    """A completed tool execution result with its message representation."""
    message: Message  # UserMessage containing ToolResultBlock(s)
    tool_use_id: str = ""


class StreamingToolExecutor:
    """Execute queued tool-use blocks with concurrency control.

    Supports two modes of operation:

    1. **Streaming mode** (matches TS): Tools are added incrementally via
       ``add_tool()`` during model streaming. ``get_completed_results()`` is
       polled synchronously during the stream to yield any finished results.
       After streaming ends, ``get_remaining_results()`` drains the rest.

    2. **Batch mode** (legacy): All tools are added, then ``get_results()``
       iterates through them.

    Parameters
    ----------
    tools:
        Registry of available Tool instances.
    context:
        Optional ToolContext forwarded to every ``tool.call()``.
    tool_executor:
        Optional ToolExecutor for permission/hook pipeline integration.
    abort_controller:
        Optional AbortController for cancellation.
    """

    def __init__(
        self,
        tools: list[Tool],
        context: ToolContext | None = None,
        tool_executor: ToolExecutor | None = None,
        abort_controller: AbortController | None = None,
    ) -> None:
        self._tools = tools
        self._context = context or ToolContext(cwd=".")
        self._tool_executor = tool_executor
        self._abort_controller = abort_controller
        self._queue: list[TrackedTool] = []
        self._yield_index: int = 0  # next index to yield in streaming mode
        self._discarded: bool = False
        # Lock to prevent concurrent exclusive tool execution
        self._exclusive_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API — streaming mode
    # ------------------------------------------------------------------

    def add_tool(self, block: ToolUseBlock) -> None:
        """Enqueue a tool-use block and start execution immediately if possible."""
        tool = find_tool_by_name(self._tools, block.name)
        concurrent_safe = True
        if tool is not None:
            if callable(getattr(tool, "is_concurrent_safe", None)):
                concurrent_safe = tool.is_concurrent_safe(block.input)
            else:
                concurrent_safe = getattr(tool, "is_concurrent_safe", True)

        tracked = TrackedTool(
            block=block,
            tool=tool,
            is_concurrent_safe=concurrent_safe,
        )
        self._queue.append(tracked)

        # Start execution immediately for concurrent-safe tools
        if not self._discarded:
            self._maybe_start_execution(tracked)

    def get_completed_results(self) -> list[ToolUpdate]:
        """Synchronously poll for completed results in queue order.

        Returns results for tools that have finished execution, up to the
        first tool that hasn't finished yet. This maintains queue ordering.
        Called during model streaming to yield results as they complete.
        """
        updates: list[ToolUpdate] = []
        while self._yield_index < len(self._queue):
            tracked = self._queue[self._yield_index]
            if tracked.status not in (ToolStatus.COMPLETED, ToolStatus.DISCARDED):
                break
            updates.append(self._make_update(tracked))
            tracked.status = ToolStatus.YIELDED
            self._yield_index += 1
        return updates

    async def get_remaining_results(self) -> AsyncGenerator[ToolUpdate, None]:
        """Wait for and yield all remaining results in queue order.

        Called after model streaming ends to drain any tools that haven't
        been yielded yet via ``get_completed_results()``.
        """
        # First, ensure all queued tools have started execution
        for tracked in self._queue[self._yield_index:]:
            if tracked.status == ToolStatus.QUEUED and not self._discarded:
                self._maybe_start_execution(tracked)

        while self._yield_index < len(self._queue):
            tracked = self._queue[self._yield_index]

            if tracked.status == ToolStatus.DISCARDED:
                yield self._make_update(tracked)
                tracked.status = ToolStatus.YIELDED
                self._yield_index += 1
                continue

            # Wait for this tool to complete
            await tracked.done_event.wait()
            yield self._make_update(tracked)
            tracked.status = ToolStatus.YIELDED
            self._yield_index += 1

    def discard(self) -> None:
        """Cancel all pending and in-progress tool executions.

        Used when a model fallback occurs and existing tool results are
        invalid (different tool_use IDs).
        """
        self._discarded = True
        for tracked in self._queue:
            if tracked.status in (ToolStatus.QUEUED, ToolStatus.EXECUTING):
                if tracked.task is not None:
                    tracked.task.cancel()
                tracked.result = ToolResult(
                    content="Discarded: tool execution cancelled",
                    is_error=True,
                )
                tracked.status = ToolStatus.DISCARDED
                tracked.done_event.set()

    # ------------------------------------------------------------------
    # Public API — batch mode (legacy, backward-compatible)
    # ------------------------------------------------------------------

    async def get_results(self) -> AsyncGenerator[ToolResult, None]:
        """Execute all queued tools and yield results in queue order.

        This is the legacy batch mode API. For streaming mode, use
        ``add_tool()`` + ``get_completed_results()`` + ``get_remaining_results()``.

        Handles tools that may have already been started by ``add_tool()``
        in streaming mode — skips re-launching them and just waits.
        """
        idx = 0
        while idx < len(self._queue):
            tracked = self._queue[idx]

            # Already completed (started by add_tool in streaming mode)
            if tracked.status in (ToolStatus.COMPLETED, ToolStatus.YIELDED):
                if tracked.status == ToolStatus.COMPLETED:
                    yield tracked.result  # type: ignore[arg-type]
                    tracked.status = ToolStatus.YIELDED
                idx += 1
                continue

            # Already executing — just wait for it
            if tracked.status == ToolStatus.EXECUTING:
                await tracked.done_event.wait()
                yield tracked.result  # type: ignore[arg-type]
                tracked.status = ToolStatus.YIELDED
                idx += 1
                continue

            if tracked.tool is None:
                tracked.result = ToolResult(
                    content=f"Tool not found: {tracked.block.name}",
                    is_error=True,
                )
                tracked.status = ToolStatus.COMPLETED
                tracked.done_event.set()
                yield tracked.result
                tracked.status = ToolStatus.YIELDED
                idx += 1
                continue

            if not tracked.is_concurrent_safe:
                await self._run_one(tracked)
                yield tracked.result  # type: ignore[arg-type]
                tracked.status = ToolStatus.YIELDED
                idx += 1
                continue

            # Gather a run of consecutive concurrent-safe QUEUED items
            batch_start = idx
            while (
                idx < len(self._queue)
                and self._queue[idx].is_concurrent_safe
                and self._queue[idx].tool is not None
                and self._queue[idx].status == ToolStatus.QUEUED
            ):
                idx += 1
            batch = self._queue[batch_start:idx]

            for t in batch:
                t.status = ToolStatus.EXECUTING
                t.task = asyncio.create_task(self._execute(t))

            for t in batch:
                await t.done_event.wait()
                yield t.result  # type: ignore[arg-type]
                t.status = ToolStatus.YIELDED

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_start_execution(self, tracked: TrackedTool) -> None:
        """Start tool execution if conditions allow.

        Concurrent-safe tools start immediately.
        Non-concurrent-safe (exclusive) tools are left QUEUED — they must
        wait until ``get_remaining_results()`` or ``get_results()`` can
        guarantee no other tool is running.
        """
        if tracked.tool is None:
            # Unknown tool — complete immediately with error
            tracked.result = ToolResult(
                content=f"Tool not found: {tracked.block.name}",
                is_error=True,
            )
            tracked.status = ToolStatus.COMPLETED
            tracked.done_event.set()
            return

        abort_signal = (
            self._abort_controller.signal if self._abort_controller else None
        )
        if abort_signal and abort_signal.aborted:
            tracked.result = ToolResult(
                content="Request interrupted by user",
                is_error=True,
            )
            tracked.status = ToolStatus.COMPLETED
            tracked.done_event.set()
            return

        # Non-concurrent-safe tools can't overlap — leave them QUEUED
        # so the drain methods handle exclusivity.
        if not tracked.is_concurrent_safe:
            return

        # Don't start concurrent tools if there are pending exclusive tools
        # ahead in the queue — they must run first to maintain ordering.
        for t in self._queue:
            if t is tracked:
                break
            if not t.is_concurrent_safe and t.status in (
                ToolStatus.QUEUED, ToolStatus.EXECUTING
            ):
                return

        tracked.status = ToolStatus.EXECUTING
        tracked.task = asyncio.create_task(self._execute(tracked))

    async def _run_one(self, tracked: TrackedTool) -> None:
        """Run a single tool synchronously (no other tasks)."""
        tracked.status = ToolStatus.EXECUTING
        try:
            tracked.result = await self._call_tool(tracked)
        except Exception as exc:
            tracked.result = ToolResult(content=str(exc), is_error=True)
        tracked.status = ToolStatus.COMPLETED
        tracked.done_event.set()

    async def _execute(self, tracked: TrackedTool) -> None:
        """Execute a tool and mark it done (for use inside asyncio.create_task)."""
        try:
            tracked.result = await self._call_tool(tracked)
        except Exception as exc:
            tracked.result = ToolResult(content=str(exc), is_error=True)
        tracked.status = ToolStatus.COMPLETED
        tracked.done_event.set()

    async def _call_tool(self, tracked: TrackedTool) -> ToolResult:
        """Call a tool through the executor pipeline or directly."""
        if self._tool_executor is not None:
            return await self._tool_executor.execute(
                tracked.tool,  # type: ignore[arg-type]
                tracked.block.input,
                self._context,
            )
        return await tracked.tool.call(  # type: ignore[union-attr]
            tracked.block.input, self._context
        )

    def _make_update(self, tracked: TrackedTool) -> ToolUpdate:
        """Convert a completed TrackedTool into a ToolUpdate with message."""
        result = tracked.result or ToolResult(
            content="No result produced", is_error=True
        )
        content = result.content if isinstance(result.content, str) else str(result.content)
        tool_result_block = ToolResultBlock(
            tool_use_id=tracked.block.id,
            content=content,
            is_error=result.is_error,
        )
        message = UserMessage(content=[tool_result_block])
        return ToolUpdate(message=message, tool_use_id=tracked.block.id)
