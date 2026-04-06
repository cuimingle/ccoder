"""Permission checker — mode-based allow/deny with path validation."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from app.settings import Settings, PermissionRule
from app.tool import ToolContext
from app.types.permissions import PermissionDecision, PermissionMode, PermissionResult

# Tools that are considered read-only (safe for plan mode)
READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob", "TaskList", "TaskGet"})

# Sensitive paths that should never be accessed
SENSITIVE_PATHS = (
    os.path.expanduser("~/.ssh"),
    os.path.expanduser("~/.aws"),
    os.path.expanduser("~/.gnupg"),
    "/etc",
)


def _get_tool_input_summary(tool_name: str, tool_input: dict) -> str:
    """Extract a representative string from tool input for pattern matching."""
    if tool_name == "Bash":
        return tool_input.get("command", "")
    if tool_name in ("Read", "Edit", "Write", "FileRead", "FileEdit", "FileWrite"):
        return tool_input.get("file_path", "")
    if tool_name in ("Grep", "Glob"):
        return tool_input.get("pattern", "")
    return str(tool_input)


def _matches_rule(rule: PermissionRule, tool_name: str, input_summary: str) -> bool:
    """Check if a permission rule matches the given tool call."""
    if not fnmatch.fnmatch(tool_name, rule.tool):
        return False
    return fnmatch.fnmatch(input_summary, rule.pattern)


def validate_path(file_path: str, cwd: str) -> str | None:
    """
    Validate a file path for security.
    Returns an error message if the path is blocked, None if ok.
    """
    if not file_path:
        return None

    try:
        resolved = Path(file_path).resolve()
    except (ValueError, OSError):
        return f"Invalid path: {file_path}"

    # Check sensitive paths
    resolved_str = str(resolved)
    for sensitive in SENSITIVE_PATHS:
        try:
            sensitive_resolved = str(Path(sensitive).resolve())
            if resolved_str.startswith(sensitive_resolved):
                return f"Access denied: {file_path} is in a sensitive directory"
        except (ValueError, OSError):
            continue

    # Check path traversal outside cwd
    try:
        cwd_resolved = str(Path(cwd).resolve())
        if not resolved_str.startswith(cwd_resolved) and not resolved_str.startswith(
            str(Path.home().resolve())
        ):
            return f"Access denied: {file_path} is outside the working directory"
    except (ValueError, OSError):
        pass

    return None


class PermissionChecker:
    """Checks permissions for tool execution based on mode and rules."""

    def __init__(self, settings: Settings, mode: PermissionMode):
        self.settings = settings
        self.mode = mode
        self._session_allow: set[str] = set()
        self._session_deny: set[str] = set()

    async def check(
        self, tool_name: str, tool_input: dict, context: ToolContext
    ) -> PermissionDecision:
        """
        Check if a tool call is allowed.

        Returns PermissionDecision with:
        - ALLOW: tool can execute
        - DENY: tool is blocked (with reason)
        """
        # Path validation for file-related tools
        file_path = tool_input.get("file_path", "")
        if file_path:
            path_error = validate_path(file_path, context.cwd)
            if path_error:
                return PermissionDecision(
                    result=PermissionResult.DENY, reason=path_error
                )

        # Check session-level overrides
        session_key = f"{tool_name}:{_get_tool_input_summary(tool_name, tool_input)}"
        if session_key in self._session_deny:
            return PermissionDecision(
                result=PermissionResult.DENY, reason="Denied for this session"
            )
        if session_key in self._session_allow:
            return PermissionDecision(result=PermissionResult.ALLOW)

        # Mode-specific logic
        if self.mode == PermissionMode.PLAN:
            return self._check_plan_mode(tool_name)
        elif self.mode == PermissionMode.AUTO:
            return self._check_auto_mode(tool_name, tool_input)
        else:
            # MANUAL mode — check rules, default to allow
            return self._check_manual_mode(tool_name, tool_input)

    def _check_plan_mode(self, tool_name: str) -> PermissionDecision:
        """Plan mode: only read-only tools allowed."""
        if tool_name in READ_ONLY_TOOLS:
            return PermissionDecision(result=PermissionResult.ALLOW)
        return PermissionDecision(
            result=PermissionResult.DENY,
            reason=f"Tool '{tool_name}' is not allowed in plan mode (read-only)",
        )

    def _check_auto_mode(
        self, tool_name: str, tool_input: dict
    ) -> PermissionDecision:
        """Auto mode: deny rules first, then allow rules, no match -> deny."""
        input_summary = _get_tool_input_summary(tool_name, tool_input)

        # Check deny rules first
        for rule in self.settings.permissions_deny:
            if _matches_rule(rule, tool_name, input_summary):
                return PermissionDecision(
                    result=PermissionResult.DENY,
                    reason=f"Matched deny rule: {rule.tool}({rule.pattern})",
                )

        # Check allow rules
        for rule in self.settings.permissions_allow:
            if _matches_rule(rule, tool_name, input_summary):
                return PermissionDecision(result=PermissionResult.ALLOW)

        # No match -> deny in auto mode
        return PermissionDecision(
            result=PermissionResult.DENY,
            reason=f"No allow rule matches {tool_name} in auto mode",
        )

    def _check_manual_mode(
        self, tool_name: str, tool_input: dict
    ) -> PermissionDecision:
        """Manual mode: check deny rules, then allow rules, default allow."""
        input_summary = _get_tool_input_summary(tool_name, tool_input)

        # Check deny rules
        for rule in self.settings.permissions_deny:
            if _matches_rule(rule, tool_name, input_summary):
                return PermissionDecision(
                    result=PermissionResult.DENY,
                    reason=f"Matched deny rule: {rule.tool}({rule.pattern})",
                )

        # Check allow rules
        for rule in self.settings.permissions_allow:
            if _matches_rule(rule, tool_name, input_summary):
                return PermissionDecision(result=PermissionResult.ALLOW)

        # No matching rule — ask the user (TUI will handle the prompt)
        return PermissionDecision(result=PermissionResult.ASK_USER)

    def record_session_decision(
        self, tool_name: str, tool_input: dict, result: PermissionResult
    ) -> None:
        """Record a session-level permission decision (allow_always/deny_always)."""
        session_key = f"{tool_name}:{_get_tool_input_summary(tool_name, tool_input)}"
        if result == PermissionResult.ALLOW_ALWAYS:
            self._session_allow.add(session_key)
            self._session_deny.discard(session_key)
        elif result == PermissionResult.DENY_ALWAYS:
            self._session_deny.add(session_key)
            self._session_allow.discard(session_key)
