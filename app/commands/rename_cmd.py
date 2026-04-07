"""Rename command handler — rename the current session."""
from __future__ import annotations

from typing import Any

from app.command_registry import CommandResult


async def rename_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Set a custom name for the current session.

    Usage:
        /rename my-session-name
    """
    if not args.strip():
        return CommandResult(text="Usage: /rename <name>")

    new_name = args.strip()
    app_state = context.get("app_state")
    if app_state is not None:
        app_state.session_name = new_name

    return CommandResult(text=f"Session renamed to: {new_name}")
