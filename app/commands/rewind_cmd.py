"""Rewind command handler — remove recent message pairs from conversation."""
from __future__ import annotations

from typing import Any

from app.command_registry import CommandResult


async def rewind_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Remove the last N user+assistant message pairs.

    Usage:
        /rewind      — remove the last exchange
        /rewind 3    — remove the last 3 exchanges
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    # Parse count first (validate args before checking state)
    count = 1
    if args.strip():
        try:
            count = int(args.strip())
            if count < 1:
                return CommandResult(text="Count must be a positive integer.")
        except ValueError:
            return CommandResult(text=f"Invalid count: {args.strip()}")

    if not engine.messages:
        return CommandResult(text="No messages to rewind.")

    # Count message pairs (user + assistant = 1 pair)
    removed = 0
    while removed < count and engine.messages:
        # Remove from the end — assistant first, then user
        if engine.messages and getattr(engine.messages[-1], "role", "") == "assistant":
            engine.messages.pop()
        if engine.messages and getattr(engine.messages[-1], "role", "") == "user":
            engine.messages.pop()
        removed += 1

    if removed == 0:
        return CommandResult(text="No message pairs to remove.")

    engine.turn_count = max(0, engine.turn_count - removed)
    return CommandResult(
        text=f"Rewound {removed} exchange(s). "
        f"Conversation now has {len(engine.messages)} messages."
    )
