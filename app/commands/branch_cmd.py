"""Branch command handler — fork the current conversation."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.command_registry import CommandResult

_SESSIONS_DIR = Path.home() / ".claude" / "sessions"


async def branch_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Fork the current conversation into a new session.

    Usage:
        /branch              — fork with auto-generated name
        /branch my-branch    — fork with custom name
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    if not engine.messages:
        return CommandResult(text="No conversation to fork.")

    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Determine branch name
    branch_name = args.strip() if args.strip() else f"branch-{str(uuid.uuid4())[:6]}"

    # Check for collision
    filepath = _SESSIONS_DIR / f"{branch_name}.json"
    if filepath.exists():
        counter = 2
        while (_SESSIONS_DIR / f"{branch_name}-{counter}.json").exists():
            counter += 1
        branch_name = f"{branch_name}-{counter}"
        filepath = _SESSIONS_DIR / f"{branch_name}.json"

    # Serialize current messages
    from app.commands.session_cmd import _serialize_messages

    ts = datetime.now(tz=timezone.utc).isoformat()
    data = {
        "session_id": branch_name,
        "timestamp": ts,
        "forked_from": getattr(engine, "_session_id", None),
        "model": engine.model,
        "cwd": engine.cwd,
        "turn_count": engine.turn_count,
        "total_input_tokens": engine.total_input_tokens,
        "total_output_tokens": engine.total_output_tokens,
        "messages": _serialize_messages(engine.messages),
    }

    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return CommandResult(
        text=f"Conversation forked as: {branch_name}\n"
        f"  Use /resume {branch_name} to switch to it."
    )
