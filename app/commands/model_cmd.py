"""Model command handler — display or switch the active model."""
from __future__ import annotations

from typing import Any

from app.command_registry import CommandResult

# Known model aliases for quick switching
_MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}


async def model_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Display or switch the current model.

    Usage:
        /model              — show current model
        /model sonnet       — switch to sonnet (alias)
        /model claude-xxx   — switch to specific model ID
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.", handled=True)

    if not args.strip():
        current = engine.model
        lines = [
            f"Current model: {current}",
            "",
            "Available aliases:",
        ]
        for alias, model_id in sorted(_MODEL_ALIASES.items()):
            marker = " (active)" if model_id == current else ""
            lines.append(f"  {alias:8s} → {model_id}{marker}")
        return CommandResult(text="\n".join(lines))

    target = args.strip().lower()

    # Resolve alias
    model_id = _MODEL_ALIASES.get(target, target)

    old_model = engine.model
    engine.model = model_id
    return CommandResult(text=f"Model changed: {old_model} → {model_id}")
