"""Tests for StreamingToolExecutor — concurrent tool execution."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.streaming_tool_executor import (
    StreamingToolExecutor,
    ToolStatus,
    TrackedTool,
)
from app.tool import ToolContext, ToolResult
from app.types.message import ToolUseBlock


# ---------------------------------------------------------------------------
# Fake tools for testing
# ---------------------------------------------------------------------------

class FakeConcurrentTool:
    """A tool that is safe to run concurrently (e.g. file read)."""

    name = "Read"
    description = "fake concurrent tool"
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    is_concurrent_safe = True

    def __init__(self, delay: float = 0.05, execution_log: list | None = None):
        self._delay = delay
        self._log = execution_log

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        if self._log is not None:
            self._log.append(("start", self.name, input.get("id", "")))
        await asyncio.sleep(self._delay)
        if self._log is not None:
            self._log.append(("end", self.name, input.get("id", "")))
        return ToolResult(content=f"ok-{input.get('id', '')}")

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)


class FakeExclusiveTool:
    """A tool that must run exclusively (e.g. bash)."""

    name = "Bash"
    description = "fake exclusive tool"
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    is_concurrent_safe = False

    def __init__(self, delay: float = 0.05, execution_log: list | None = None):
        self._delay = delay
        self._log = execution_log

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        if self._log is not None:
            self._log.append(("start", self.name, input.get("id", "")))
        await asyncio.sleep(self._delay)
        if self._log is not None:
            self._log.append(("end", self.name, input.get("id", "")))
        return ToolResult(content=f"bash-{input.get('id', '')}")

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_safe_tools_run_in_parallel():
    """Three concurrent-safe Read tools should overlap in execution."""
    execution_log: list[tuple[str, str, str]] = []
    tool = FakeConcurrentTool(delay=0.1, execution_log=execution_log)
    executor = StreamingToolExecutor(tools=[tool])

    blocks = [
        ToolUseBlock(id=f"t{i}", name="Read", input={"id": str(i)})
        for i in range(3)
    ]
    for b in blocks:
        executor.add_tool(b)

    results = []
    async for r in executor.get_results():
        results.append(r)

    # All three should complete
    assert len(results) == 3
    # Results should be in queue order
    assert results[0].content == "ok-0"
    assert results[1].content == "ok-1"
    assert results[2].content == "ok-2"

    # Verify parallelism: all starts happen before any end
    starts = [e for e in execution_log if e[0] == "start"]
    ends = [e for e in execution_log if e[0] == "end"]
    assert len(starts) == 3
    assert len(ends) == 3
    # Since they run concurrently, all 3 starts should appear before the first end
    start_indices = [execution_log.index(s) for s in starts]
    end_indices = [execution_log.index(e) for e in ends]
    assert max(start_indices) < min(end_indices)


@pytest.mark.asyncio
async def test_non_concurrent_tools_run_sequentially():
    """Two exclusive Bash tools must run one after the other."""
    execution_log: list[tuple[str, str, str]] = []
    tool = FakeExclusiveTool(delay=0.05, execution_log=execution_log)
    executor = StreamingToolExecutor(tools=[tool])

    blocks = [
        ToolUseBlock(id="b1", name="Bash", input={"id": "1"}),
        ToolUseBlock(id="b2", name="Bash", input={"id": "2"}),
    ]
    for b in blocks:
        executor.add_tool(b)

    results = []
    async for r in executor.get_results():
        results.append(r)

    assert len(results) == 2
    assert results[0].content == "bash-1"
    assert results[1].content == "bash-2"

    # Verify sequential: first tool ends before second starts
    assert execution_log == [
        ("start", "Bash", "1"),
        ("end", "Bash", "1"),
        ("start", "Bash", "2"),
        ("end", "Bash", "2"),
    ]


@pytest.mark.asyncio
async def test_mixed_concurrent_and_exclusive():
    """Bash (exclusive) then 2 Reads (concurrent).

    The Bash must finish before the Reads start, but the two Reads run in parallel.
    """
    execution_log: list[tuple[str, str, str]] = []
    bash_tool = FakeExclusiveTool(delay=0.05, execution_log=execution_log)
    read_tool = FakeConcurrentTool(delay=0.1, execution_log=execution_log)
    executor = StreamingToolExecutor(tools=[bash_tool, read_tool])

    executor.add_tool(ToolUseBlock(id="b1", name="Bash", input={"id": "b"}))
    executor.add_tool(ToolUseBlock(id="r1", name="Read", input={"id": "1"}))
    executor.add_tool(ToolUseBlock(id="r2", name="Read", input={"id": "2"}))

    results = []
    async for r in executor.get_results():
        results.append(r)

    assert len(results) == 3
    assert results[0].content == "bash-b"
    assert results[1].content == "ok-1"
    assert results[2].content == "ok-2"

    # Bash ends before any Read starts
    bash_end_idx = execution_log.index(("end", "Bash", "b"))
    read_starts = [
        execution_log.index(e) for e in execution_log
        if e[0] == "start" and e[1] == "Read"
    ]
    assert all(idx > bash_end_idx for idx in read_starts)

    # Both reads start before either finishes (parallel)
    read_ends = [
        execution_log.index(e) for e in execution_log
        if e[0] == "end" and e[1] == "Read"
    ]
    assert max(read_starts) < min(read_ends)


@pytest.mark.asyncio
async def test_tool_not_found_returns_error():
    """If a tool name is not in the registry, return an error ToolResult."""
    executor = StreamingToolExecutor(tools=[])

    executor.add_tool(ToolUseBlock(id="x1", name="NoSuchTool", input={}))

    results = []
    async for r in executor.get_results():
        results.append(r)

    assert len(results) == 1
    assert results[0].is_error is True
    assert "not found" in results[0].content.lower()
