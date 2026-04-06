"""Tool orchestration — concurrent/serial batch execution.

Provides a non-streaming tool execution path as a fallback when
``StreamingToolExecutor`` is not used.  Matches the TypeScript
``toolOrchestration.ts`` partitioning and execution model.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator

from app.tool import ToolResult, find_tool_by_name
from app.types.message import ToolResultBlock, ToolUseBlock, UserMessage

if TYPE_CHECKING:
    from app.abort import AbortSignal
    from app.tool import Tool, ToolContext
    from app.tool_executor import ToolExecutor

MAX_CONCURRENCY = int(os.environ.get("CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY", "10"))


@dataclass
class ToolBatch:
    """A group of tool-use blocks that can be executed together."""
    blocks: list[ToolUseBlock]
    is_concurrent_safe: bool


@dataclass
class ToolResultUpdate:
    """A single tool execution result yielded from the orchestrator."""
    message: UserMessage
    context_modifier: object | None = None  # Callable[[ToolContext], ToolContext] | None


def partition_tool_calls(
    blocks: list[ToolUseBlock],
    tools: list[Tool],
) -> list[ToolBatch]:
    """Group consecutive tool-use blocks into concurrent-safe batches.

    Algorithm (matches TypeScript):
    - Reduce tool calls into batches where each batch is either:
      - A maximal run of consecutive concurrent-safe tools (run in parallel)
      - A single non-concurrent-safe tool (run alone)
    """
    if not blocks:
        return []

    batches: list[ToolBatch] = []

    for block in blocks:
        tool = find_tool_by_name(tools, block.name)
        is_safe = True
        if tool is not None:
            try:
                is_safe = tool.is_concurrent_safe()
            except Exception:
                is_safe = False  # Conservative: treat as exclusive

        if is_safe and batches and batches[-1].is_concurrent_safe:
            # Extend the current concurrent batch
            batches[-1].blocks.append(block)
        else:
            batches.append(ToolBatch(blocks=[block], is_concurrent_safe=is_safe))

    return batches


async def run_tools(
    blocks: list[ToolUseBlock],
    tools: list[Tool],
    context: ToolContext,
    tool_executor: ToolExecutor | None = None,
    abort_signal: AbortSignal | None = None,
    max_concurrency: int = MAX_CONCURRENCY,
) -> AsyncIterator[ToolResultUpdate]:
    """Execute tool-use blocks and yield results.

    Partitions into batches and executes each batch either concurrently or
    serially.  Batches are processed sequentially relative to each other.
    """
    batches = partition_tool_calls(blocks, tools)

    for batch in batches:
        if abort_signal and abort_signal.aborted:
            # Yield error results for remaining blocks
            for block in batch.blocks:
                yield _error_result(block, "Interrupted by user")
            continue

        if batch.is_concurrent_safe and len(batch.blocks) > 1:
            # Run concurrently with concurrency limit
            async for update in _run_concurrent(
                batch.blocks, tools, context, tool_executor, max_concurrency
            ):
                yield update
        else:
            # Run serially (single block or non-concurrent-safe)
            for block in batch.blocks:
                if abort_signal and abort_signal.aborted:
                    yield _error_result(block, "Interrupted by user")
                    continue
                yield await _run_single(block, tools, context, tool_executor)


async def _run_concurrent(
    blocks: list[ToolUseBlock],
    tools: list[Tool],
    context: ToolContext,
    tool_executor: ToolExecutor | None,
    max_concurrency: int,
) -> AsyncIterator[ToolResultUpdate]:
    """Run a batch of concurrent-safe tools in parallel."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _execute(block: ToolUseBlock) -> ToolResultUpdate:
        async with semaphore:
            return await _run_single(block, tools, context, tool_executor)

    tasks = [asyncio.create_task(_execute(b)) for b in blocks]

    # Yield in original order (not completion order) to preserve determinism
    for task in tasks:
        result = await task
        yield result


async def _run_single(
    block: ToolUseBlock,
    tools: list[Tool],
    context: ToolContext,
    tool_executor: ToolExecutor | None,
) -> ToolResultUpdate:
    """Run a single tool and return the result."""
    tool = find_tool_by_name(tools, block.name)
    if tool is None:
        return _error_result(block, f"Tool not found: {block.name}")

    try:
        if tool_executor is not None:
            result = await tool_executor.execute(tool, block.input, context)
        else:
            result = await tool.call(block.input, context)
    except Exception as exc:
        result = ToolResult(content=str(exc), is_error=True)

    content = result.content if isinstance(result.content, str) else str(result.content)
    msg = UserMessage(
        content=[
            ToolResultBlock(
                tool_use_id=block.id,
                content=content,
                is_error=result.is_error,
            )
        ]
    )
    return ToolResultUpdate(message=msg)


def _error_result(block: ToolUseBlock, error_message: str) -> ToolResultUpdate:
    """Create an error ToolResultUpdate for a failed/skipped tool."""
    msg = UserMessage(
        content=[
            ToolResultBlock(
                tool_use_id=block.id,
                content=error_message,
                is_error=True,
            )
        ]
    )
    return ToolResultUpdate(message=msg)
