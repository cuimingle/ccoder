"""Tool executor — orchestrates permission check, hooks, and tool execution."""
from __future__ import annotations

from typing import Awaitable, Callable

from app.hooks import HookRunner
from app.permissions import PermissionChecker
from app.tool import Tool, ToolContext, ToolResult
from app.types.permissions import PermissionResult

# Callback type: (tool_name, tool_input) -> PermissionResult
PermissionCallback = Callable[[str, dict], Awaitable[PermissionResult]]


class ToolExecutor:
    """
    Wraps tool execution with permission checks and hooks.

    Pipeline: permission check -> pre-hooks -> tool.call() -> post-hooks
    """

    def __init__(
        self,
        permission_checker: PermissionChecker,
        hook_runner: HookRunner,
        permission_callback: PermissionCallback | None = None,
    ):
        self.permission_checker = permission_checker
        self.hook_runner = hook_runner
        self._permission_callback = permission_callback

    async def execute(
        self, tool: Tool, tool_input: dict, context: ToolContext
    ) -> ToolResult:
        """
        Execute a tool with permission and hook checks.

        Returns ToolResult — either from the tool itself or an error
        if permission is denied or a hook aborts execution.
        """
        # 1. Permission check
        decision = await self.permission_checker.check(
            tool.name, tool_input, context
        )
        if decision.result in (PermissionResult.DENY, PermissionResult.DENY_ALWAYS):
            return ToolResult(
                content=f"Permission denied: {decision.reason}",
                is_error=True,
            )

        if decision.result == PermissionResult.ASK_USER:
            if self._permission_callback is not None:
                user_result = await self._permission_callback(tool.name, tool_input)
                if user_result in (PermissionResult.DENY, PermissionResult.DENY_ALWAYS):
                    self.permission_checker.record_session_decision(
                        tool.name, tool_input, user_result
                    )
                    return ToolResult(
                        content="Permission denied by user.", is_error=True
                    )
                if user_result == PermissionResult.ALLOW_ALWAYS:
                    self.permission_checker.record_session_decision(
                        tool.name, tool_input, user_result
                    )
            # No callback (pipe mode) or user allowed — proceed

        # 2. Pre-hooks
        hook_result = await self.hook_runner.run_pre_hooks(tool.name, tool_input)
        if not hook_result.proceed:
            return ToolResult(
                content=f"Blocked by hook: {hook_result.message}",
                is_error=True,
            )

        # 3. Execute tool
        try:
            result = await tool.call(tool_input, context)
        except Exception as e:
            result = ToolResult(content=str(e), is_error=True)

        # 4. Post-hooks (fire & forget — errors logged, don't affect result)
        await self.hook_runner.run_post_hooks(tool.name, tool_input, result)

        return result
