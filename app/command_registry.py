"""Extensible command registry for slash commands."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class CommandResult:
    """Result of a slash command execution."""

    text: str
    handled: bool = True
    should_query: bool = False
    prompt_content: str = ""
    should_exit: bool = False


@dataclass
class LocalCommand:
    """A command that executes locally and returns a result directly."""

    name: str
    description: str
    handler: Callable[[str, dict[str, Any]], Awaitable[CommandResult]]
    aliases: list[str] = field(default_factory=list)
    is_hidden: bool = False
    type: str = field(default="local", init=False)


@dataclass
class PromptCommand:
    """A command that generates a prompt to be sent to the model."""

    name: str
    description: str
    get_prompt: Callable[[str], Awaitable[str]]
    progress_message: str = ""
    aliases: list[str] = field(default_factory=list)
    is_hidden: bool = False
    type: str = field(default="prompt", init=False)


# Type alias
Command = LocalCommand | PromptCommand


class CommandRegistry:
    """Registry for slash commands, supporting lookup by name or alias."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: Command) -> None:
        """Register a command by its name and all aliases."""
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    def get(self, name: str) -> Command | None:
        """Look up a command by name or alias. Returns None if not found."""
        if name in self._commands:
            return self._commands[name]
        canonical = self._aliases.get(name)
        if canonical is not None:
            return self._commands.get(canonical)
        return None

    def list_commands(self) -> list[Command]:
        """Return all non-hidden commands."""
        return [cmd for cmd in self._commands.values() if not cmd.is_hidden]

    async def execute(
        self, name: str, args: str, context: dict[str, Any]
    ) -> CommandResult:
        """Dispatch a command by name. Returns a CommandResult."""
        command = self.get(name)
        if command is None:
            return CommandResult(
                text=f"Unknown command: /{name}", handled=False
            )

        if isinstance(command, LocalCommand):
            return await command.handler(args, context)

        # PromptCommand
        prompt = await command.get_prompt(args)
        return CommandResult(
            text=command.progress_message or f"Running /{command.name}...",
            handled=True,
            should_query=True,
            prompt_content=prompt,
        )
