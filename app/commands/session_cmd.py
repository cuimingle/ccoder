"""Session and resume command handlers — save/load conversation sessions."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.command_registry import CommandResult

_SESSIONS_DIR = Path.home() / ".claude" / "sessions"


def _ensure_sessions_dir() -> Path:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSIONS_DIR


def _serialize_messages(messages: list) -> list[dict]:
    """Serialize Message objects to JSON-friendly dicts."""
    result = []
    for msg in messages:
        entry: dict[str, Any] = {"role": getattr(msg, "role", "unknown")}
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            entry["content"] = content
        elif isinstance(content, list):
            entry["content"] = [
                part if isinstance(part, dict) else str(part)
                for part in content
            ]
        else:
            entry["content"] = str(content)
        result.append(entry)
    return result


async def session_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Save the current session to disk.

    Usage:
        /session             — save with auto-generated ID
        /session my-session  — save with custom name
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    if not engine.messages:
        return CommandResult(text="No conversation to save.")

    sessions_dir = _ensure_sessions_dir()
    session_id = args.strip() or str(uuid.uuid4())[:8]
    ts = datetime.now(tz=timezone.utc).isoformat()

    data = {
        "session_id": session_id,
        "timestamp": ts,
        "model": engine.model,
        "cwd": engine.cwd,
        "turn_count": engine.turn_count,
        "total_input_tokens": engine.total_input_tokens,
        "total_output_tokens": engine.total_output_tokens,
        "messages": _serialize_messages(engine.messages),
    }

    filepath = sessions_dir / f"{session_id}.json"
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return CommandResult(text=f"Session saved: {session_id}\n  Path: {filepath}")


async def resume_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Resume a saved session.

    Usage:
        /resume              — list available sessions
        /resume <session_id> — resume a specific session
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    sessions_dir = _ensure_sessions_dir()

    if not args.strip():
        # List available sessions
        files = sorted(sessions_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return CommandResult(text="No saved sessions found.")

        lines = ["Available sessions:"]
        for f in files[:20]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sid = data.get("session_id", f.stem)
                ts = data.get("timestamp", "?")
                turns = data.get("turn_count", 0)
                lines.append(f"  {sid}  ({turns} turns, {ts})")
            except (json.JSONDecodeError, OSError):
                lines.append(f"  {f.stem}  (corrupted)")
        lines.append("\nUsage: /resume <session_id>")
        return CommandResult(text="\n".join(lines))

    # Resume specific session
    session_id = args.strip()
    filepath = sessions_dir / f"{session_id}.json"
    if not filepath.exists():
        return CommandResult(text=f"Session not found: {session_id}")

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return CommandResult(text=f"Error loading session: {e}")

    # Restore engine state
    from app.types.message import UserMessage, AssistantMessage, TextBlock

    engine.messages = []
    for msg_data in data.get("messages", []):
        role = msg_data.get("role", "user")
        content = msg_data.get("content", "")
        if role == "user":
            engine.messages.append(UserMessage(content=content))
        elif role == "assistant":
            # AssistantMessage.content must be list[ContentBlock]
            if isinstance(content, str):
                content = [TextBlock(text=content)]
            elif isinstance(content, list):
                content = [TextBlock(text=str(c)) for c in content]
            engine.messages.append(AssistantMessage(content=content))

    engine.turn_count = data.get("turn_count", 0)
    engine.total_input_tokens = data.get("total_input_tokens", 0)
    engine.total_output_tokens = data.get("total_output_tokens", 0)

    return CommandResult(
        text=f"Session resumed: {session_id} ({engine.turn_count} turns, "
        f"{engine.total_input_tokens:,} input tokens)"
    )
