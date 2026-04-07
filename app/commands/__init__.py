"""Slash command dispatcher and default registry builder."""
from __future__ import annotations

from typing import Any

from app.command_registry import CommandRegistry, CommandResult, LocalCommand

# --- Command handlers ---
from app.commands.cost import cost_handler
from app.commands.help import help_handler
from app.commands.exit_cmd import exit_handler
from app.commands.model_cmd import model_handler
from app.commands.diff_cmd import diff_handler
from app.commands.export_cmd import export_handler
from app.commands.session_cmd import session_handler, resume_handler
from app.commands.rewind_cmd import rewind_handler
from app.commands.branch_cmd import branch_handler
from app.commands.rename_cmd import rename_handler
from app.commands.config_commands import (
    permissions_handler,
    hooks_handler,
    config_handler,
)
from app.commands.info_commands import (
    stats_handler,
    status_handler,
    doctor_handler,
    context_handler,
    usage_handler,
)
from app.commands.env_commands import (
    add_dir_handler,
    files_handler,
    cwd_handler,
)


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


KNOWN_COMMANDS = {
    "clear", "compact", "help", "cost",
    "exit", "quit", "model", "diff", "export",
    "session", "resume", "rewind", "branch", "rename",
    "permissions", "hooks", "config",
    "stats", "status", "doctor", "context", "usage",
    "add-dir", "files", "cwd",
}


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

    # --- Session management ---
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
        name="exit",
        description="Exit the application",
        handler=exit_handler,
        aliases=["quit", "q"],
    ))
    registry.register(LocalCommand(
        name="session",
        description="Save current session",
        handler=session_handler,
    ))
    registry.register(LocalCommand(
        name="resume",
        description="Resume a saved session",
        handler=resume_handler,
        aliases=["continue"],
    ))
    registry.register(LocalCommand(
        name="rewind",
        description="Remove last N message exchanges",
        handler=rewind_handler,
    ))
    registry.register(LocalCommand(
        name="branch",
        description="Fork conversation into a new session",
        handler=branch_handler,
        aliases=["fork"],
    ))
    registry.register(LocalCommand(
        name="rename",
        description="Rename the current session",
        handler=rename_handler,
    ))

    # --- Model & query ---
    registry.register(LocalCommand(
        name="model",
        description="Display or switch the active model",
        handler=model_handler,
    ))

    # --- Code & files ---
    registry.register(LocalCommand(
        name="diff",
        description="Show git diff output",
        handler=diff_handler,
    ))
    registry.register(LocalCommand(
        name="export",
        description="Export conversation to a file",
        handler=export_handler,
    ))

    # --- Info ---
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
    registry.register(LocalCommand(
        name="stats",
        description="Show extended session statistics",
        handler=stats_handler,
    ))
    registry.register(LocalCommand(
        name="status",
        description="Show system status",
        handler=status_handler,
    ))
    registry.register(LocalCommand(
        name="doctor",
        description="Run diagnostic checks",
        handler=doctor_handler,
    ))
    registry.register(LocalCommand(
        name="context",
        description="Show current context information",
        handler=context_handler,
    ))
    registry.register(LocalCommand(
        name="usage",
        description="Show API usage summary",
        handler=usage_handler,
    ))

    # --- Config ---
    registry.register(LocalCommand(
        name="permissions",
        description="Display permission rules",
        handler=permissions_handler,
        aliases=["allowed-tools"],
    ))
    registry.register(LocalCommand(
        name="hooks",
        description="Display configured hooks",
        handler=hooks_handler,
    ))
    registry.register(LocalCommand(
        name="config",
        description="Display current settings",
        handler=config_handler,
        aliases=["settings"],
    ))

    # --- Environment ---
    registry.register(LocalCommand(
        name="add-dir",
        description="Add an additional working directory",
        handler=add_dir_handler,
    ))
    registry.register(LocalCommand(
        name="files",
        description="List files referenced in conversation",
        handler=files_handler,
    ))
    registry.register(LocalCommand(
        name="cwd",
        description="Display or change working directory",
        handler=cwd_handler,
    ))

    return registry
