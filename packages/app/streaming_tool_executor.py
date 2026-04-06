"""StreamingToolExecutor — concurrent tool execution with ordering guarantees.

Tools marked ``is_concurrent_safe = True`` may overlap execution.
Tools marked ``is_concurrent_safe = False`` run exclusively (nothing else runs
while they are executing).  Queue order is always respected for yielding
results.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator

from app.tool import Tool, ToolContext, ToolResult, find_tool_by_name
from app.types.message import ToolUseBlock


class ToolStatus(Enum):
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    YIELDED = "yielded"


@dataclass
class TrackedTool:
    block: ToolUseBlock
    tool: Tool | None
    status: ToolStatus = ToolStatus.QUEUED
    is_concurrent_safe: bool = True
    result: ToolResult | None = None
    task: asyncio.Task | None = None  # type: ignore[type-arg]
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


class StreamingToolExecutor:
    """Execute queued tool-use blocks with concurrency control.

    Parameters
    ----------
    tools:
        Registry of available Tool instances.
    context:
        Optional ToolContext forwarded to every ``tool.call()``.
    """

    def __init__(
        self,
        tools: list[Tool],
        context: ToolContext | None = None,
    ) -> None:
        self._tools = tools
        self._context = context or ToolContext(cwd=".")
        self._queue: list[TrackedTool] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_tool(self, block: ToolUseBlock) -> None:
        """Enqueue a tool-use block for later execution."""
        tool = find_tool_by_name(self._tools, block.name)
        # Support both method (new) and attribute (legacy) forms
        if tool is not None:
            if callable(getattr(tool, "is_concurrent_safe", None)):
                concurrent_safe = tool.is_concurrent_safe(block.input)
            else:
                concurrent_safe = getattr(tool, "is_concurrent_safe", True)
        else:
            concurrent_safe = True
        self._queue.append(
            TrackedTool(
                block=block,
                tool=tool,
                is_concurrent_safe=concurrent_safe,
            )
        )

    async def get_results(self) -> AsyncGenerator[ToolResult, None]:
        """Execute all queued tools and yield results in queue order."""
        # We process the queue in segments.  A segment is either:
        #   - a maximal run of consecutive concurrent-safe items, OR
        #   - a single non-concurrent-safe (exclusive) item.
        #
        # Segments execute sequentially relative to each other, but items
        # within a concurrent segment run in parallel.

        idx = 0
        while idx < len(self._queue):
            tracked = self._queue[idx]

            if tracked.tool is None:
                # Unknown tool — produce error immediately
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
                # Exclusive tool — run alone
                await self._run_one(tracked)
                yield tracked.result  # type: ignore[arg-type]
                tracked.status = ToolStatus.YIELDED
                idx += 1
                continue

            # Gather a run of concurrent-safe items starting at idx
            batch_start = idx
            while (
                idx < len(self._queue)
                and self._queue[idx].is_concurrent_safe
                and self._queue[idx].tool is not None
            ):
                idx += 1
            batch = self._queue[batch_start:idx]

            # Launch all concurrently
            for t in batch:
                t.status = ToolStatus.EXECUTING
                t.task = asyncio.create_task(self._execute(t))

            # Yield in queue order (wait for each)
            for t in batch:
                await t.done_event.wait()
                yield t.result  # type: ignore[arg-type]
                t.status = ToolStatus.YIELDED

            # idx already advanced past the batch

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_one(self, tracked: TrackedTool) -> None:
        """Run a single tool synchronously (no other tasks)."""
        tracked.status = ToolStatus.EXECUTING
        try:
            tracked.result = await tracked.tool.call(  # type: ignore[union-attr]
                tracked.block.input, self._context
            )
        except Exception as exc:
            tracked.result = ToolResult(content=str(exc), is_error=True)
        tracked.status = ToolStatus.COMPLETED
        tracked.done_event.set()

    async def _execute(self, tracked: TrackedTool) -> None:
        """Execute a tool and mark it done (for use inside asyncio.create_task)."""
        try:
            tracked.result = await tracked.tool.call(  # type: ignore[union-attr]
                tracked.block.input, self._context
            )
        except Exception as exc:
            tracked.result = ToolResult(content=str(exc), is_error=True)
        tracked.status = ToolStatus.COMPLETED
        tracked.done_event.set()
