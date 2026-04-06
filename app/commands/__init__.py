"""Slash command dispatcher and default registry builder."""
from __future__ import annotations

from typing import Any

from app.command_registry import CommandRegistry, CommandResult, LocalCommand
from app.commands.cost import cost_handler
from app.commands.help import help_handler


# ---------------------------------------------------------------------------
# Parsing helpers (used by QueryEngine and tests)
# ---------------------------------------------------------------------------

def parse_command(user_input: str) -> tuple[str, str] | None:
    """
    Parse a slash command from user input.
    Returns (command_name, args) or None if not a command.
    """
    stripped = user_input.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.split(None, 1)
    command = parts[0][1:]  # remove leading /
    args = parts[1] if len(parts) > 1 else ""
    return command, args


KNOWN_COMMANDS = {"compact", "clear", "help", "cost"}


def is_command(user_input: str) -> bool:
    """Check if user input is a slash command."""
    return parse_command(user_input) is not None


# ---------------------------------------------------------------------------
# Default registry builder
# ---------------------------------------------------------------------------

async def _clear_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Clear conversation history."""
    return CommandResult(text="Session cleared.")


async def _compact_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Compact conversation context (placeholder – actual compaction handled by QueryEngine)."""
    return CommandResult(text="Compacting conversation context...")


def build_default_registry() -> CommandRegistry:
    """Create a CommandRegistry pre-populated with the built-in commands."""
    registry = CommandRegistry()

    registry.register(LocalCommand(
        name="clear",
        description="Clear conversation history",
        handler=_clear_handler,
    ))

    registry.register(LocalCommand(
        name="compact",
        description="Compact conversation context",
        handler=_compact_handler,
    ))

    registry.register(LocalCommand(
        name="cost",
        description="Show token usage and cost",
        handler=cost_handler,
    ))

    registry.register(LocalCommand(
        name="help",
        description="Show available commands",
        handler=help_handler,
        aliases=["h", "?"],
    ))

    return registry
