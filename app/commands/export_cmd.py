"""Export command handler — export conversation to a file."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.command_registry import CommandResult


def _render_messages_to_text(messages: list) -> str:
    """Render conversation messages to plain text."""
    lines: list[str] = []
    for msg in messages:
        role = getattr(msg, "role", "unknown")
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            # Multi-part content (tool use blocks, etc.)
            parts = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(part.get("text", str(part)))
                else:
                    parts.append(str(part))
            content = "\n".join(parts)

        if role == "user":
            lines.append(f"## User\n\n{content}\n")
        elif role == "assistant":
            lines.append(f"## Assistant\n\n{content}\n")
        else:
            lines.append(f"## {role.title()}\n\n{content}\n")
    return "\n".join(lines)


async def export_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Export the conversation to a markdown file.

    Usage:
        /export              — auto-generate filename with timestamp
        /export myfile.md    — export to specific file
    """
    engine = context.get("engine")
    cwd = context.get("cwd", ".")

    if engine is None or not engine.messages:
        return CommandResult(text="No conversation to export.")

    text = _render_messages_to_text(engine.messages)

    if args.strip():
        filename = args.strip()
    else:
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        filename = f"claude-conversation-{ts}.md"

    filepath = Path(cwd) / filename
    filepath.write_text(text, encoding="utf-8")

    rel = os.path.relpath(filepath, cwd)
    return CommandResult(text=f"Conversation exported to {rel}")
