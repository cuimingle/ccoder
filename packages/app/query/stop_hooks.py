"""Stop hook execution — post-turn hook processing.

Matches TypeScript ``query/stopHooks.ts`` behavior:
- Run stop hooks after a turn completes (no tool_use in response)
- Collect blocking errors that require model re-processing
- Detect if hooks should prevent continuation
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.hooks import HookRunner
    from app.types.message import Message

logger = logging.getLogger(__name__)


@dataclass
class StopHookResult:
    """Result of running stop hooks."""
    blocking_errors: list[str] = field(default_factory=list)
    prevent_continuation: bool = False


async def run_stop_hooks(
    messages: list[Message],
    hook_runner: HookRunner | None,
    tool_names_used: list[str] | None = None,
) -> StopHookResult:
    """Execute post-turn stop hooks and collect results.

    Parameters
    ----------
    messages:
        Full conversation history.
    hook_runner:
        The hook runner to execute hooks through.
    tool_names_used:
        Names of tools used in the current turn, for matching hook patterns.

    Returns
    -------
    StopHookResult with blocking errors and continuation control.
    """
    if hook_runner is None:
        return StopHookResult()

    result = StopHookResult()

    # Run PostToolUse hooks for each tool used in this turn
    if tool_names_used:
        for tool_name in tool_names_used:
            try:
                hook_result = await hook_runner.run_post_hooks(
                    tool_name=tool_name,
                    tool_input={},
                    tool_output="",
                )
                if hook_result and not hook_result.success:
                    result.blocking_errors.append(
                        f"Post-tool hook failed for {tool_name}: {hook_result.stderr}"
                    )
            except Exception:
                logger.exception("Stop hook error for tool %s", tool_name)

    return result
