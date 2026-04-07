"""Exit command handler — gracefully exit the REPL."""
from __future__ import annotations

import random
from typing import Any

from app.command_registry import CommandResult

_GOODBYE_MESSAGES = [
    "Goodbye! Happy coding!",
    "See you later!",
    "Until next time!",
    "Bye! Keep building great things!",
    "Farewell, fellow coder!",
]


async def exit_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Exit the application."""
    msg = random.choice(_GOODBYE_MESSAGES)
    return CommandResult(text=msg, handled=True, should_exit=True)
