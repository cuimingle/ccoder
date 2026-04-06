"""Hook runner — execute shell hooks before/after tool calls."""
from __future__ import annotations

import asyncio
import json
import fnmatch
import logging
from dataclasses import dataclass

from app.settings import HookConfig
from app.tool import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class HookResult:
    """Result of running pre-hooks."""

    proceed: bool = True
    message: str = ""


class HookRunner:
    """Executes shell-command hooks for tool calls."""

    def __init__(self, hooks: list[HookConfig]):
        self._hooks = hooks

    def _matching_hooks(self, event: str, tool_name: str) -> list[HookConfig]:
        """Find hooks matching the given event and tool name."""
        return [
            h
            for h in self._hooks
            if h.event == event and fnmatch.fnmatch(tool_name, h.matcher)
        ]

    async def _run_hook_command(
        self, hook: HookConfig, stdin_data: dict
    ) -> tuple[int, str, str]:
        """
        Run a single hook command.
        Returns (return_code, stdout, stderr).
        """
        stdin_bytes = json.dumps(stdin_data, default=str).encode("utf-8")

        proc = await asyncio.create_subprocess_shell(
            hook.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=hook.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return -1, "", f"Hook timed out after {hook.timeout}s: {hook.command}"

        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    async def run_pre_hooks(
        self, tool_name: str, tool_input: dict
    ) -> HookResult:
        """
        Run PreToolUse hooks. If any hook exits non-zero, abort.
        Returns HookResult(proceed=True) if all hooks pass.
        """
        hooks = self._matching_hooks("PreToolUse", tool_name)
        if not hooks:
            return HookResult()

        stdin_data = {"tool_name": tool_name, "tool_input": tool_input}

        for hook in hooks:
            returncode, stdout, stderr = await self._run_hook_command(
                hook, stdin_data
            )
            if returncode != 0:
                message = stderr.strip() or stdout.strip() or f"Hook exited with code {returncode}"
                return HookResult(proceed=False, message=message)

        return HookResult()

    async def run_post_hooks(
        self, tool_name: str, tool_input: dict, tool_result: ToolResult
    ) -> None:
        """
        Run PostToolUse hooks. Errors are logged but don't affect flow.
        """
        hooks = self._matching_hooks("PostToolUse", tool_name)
        if not hooks:
            return

        result_content = (
            tool_result.content
            if isinstance(tool_result.content, str)
            else str(tool_result.content)
        )
        stdin_data = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_result": {
                "content": result_content[:5000],  # limit size for hook stdin
                "is_error": tool_result.is_error,
            },
        }

        for hook in hooks:
            try:
                returncode, stdout, stderr = await self._run_hook_command(
                    hook, stdin_data
                )
                if returncode != 0:
                    logger.warning(
                        "PostToolUse hook failed (rc=%d): %s — %s",
                        returncode,
                        hook.command,
                        stderr.strip(),
                    )
            except Exception as e:
                logger.warning("PostToolUse hook error: %s — %s", hook.command, e)
