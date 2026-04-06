"""Help command handler – lists available slash commands."""
from __future__ import annotations

from typing import Any

from app.command_registry import CommandRegistry, CommandResult


async def help_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """List all registered slash commands."""
    registry: CommandRegistry | None = context.get("registry")

    if registry is not None:
        commands = registry.list_commands()
        lines = ["Available commands:"]
        for cmd in sorted(commands, key=lambda c: c.name):
            alias_str = ""
            if cmd.aliases:
                alias_str = " (aliases: " + ", ".join(f"/{a}" for a in cmd.aliases) + ")"
            lines.append(f"  /{cmd.name} – {cmd.description}{alias_str}")
        return CommandResult(text="\n".join(lines))

    # Fallback when no registry is available
    fallback = [
        "Available commands:",
        "  /clear – Clear conversation history",
        "  /compact – Compact conversation context",
        "  /cost – Show token usage and cost",
        "  /help – Show this help message",
    ]
    return CommandResult(text="\n".join(fallback))
