"""Environment-related command handlers — /add-dir, /files, /cwd."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.command_registry import CommandResult


async def add_dir_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Add an additional working directory to the context.

    Usage:
        /add-dir /path/to/other/project
    """
    if not args.strip():
        return CommandResult(text="Usage: /add-dir <path>")

    target = Path(args.strip()).expanduser().resolve()
    if not target.is_dir():
        return CommandResult(text=f"Not a directory: {target}")

    app_state = context.get("app_state")
    if app_state is not None:
        if not hasattr(app_state, "extra_dirs"):
            app_state.extra_dirs = []
        if str(target) not in app_state.extra_dirs:
            app_state.extra_dirs.append(str(target))
            return CommandResult(text=f"Added directory: {target}")
        return CommandResult(text=f"Directory already added: {target}")

    return CommandResult(text=f"Directory noted: {target} (state unavailable)")


async def files_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """List files referenced in the conversation.

    Usage:
        /files
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    # Collect file paths from tool calls in messages
    file_paths: set[str] = set()
    cwd = context.get("cwd", ".")

    for msg in engine.messages:
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    # Tool use blocks may contain file_path
                    inp = block.get("input", {})
                    if isinstance(inp, dict):
                        for key in ("file_path", "path", "file"):
                            val = inp.get(key)
                            if val and isinstance(val, str):
                                file_paths.add(val)
                    # Tool result blocks may mention paths
                    text = block.get("text", "")
                    if isinstance(text, str) and "/" in text:
                        # Simple heuristic: extract lines that look like file paths
                        for line in text.split("\n"):
                            line = line.strip()
                            if line.startswith("/") and len(line) < 200 and " " not in line:
                                file_paths.add(line)

    if not file_paths:
        return CommandResult(text="No files referenced in conversation.")

    # Make paths relative to cwd where possible
    rel_paths = []
    for fp in sorted(file_paths):
        try:
            rel = os.path.relpath(fp, cwd)
            rel_paths.append(rel)
        except ValueError:
            rel_paths.append(fp)

    lines = [f"Files in context ({len(rel_paths)}):"]
    for rp in rel_paths:
        lines.append(f"  {rp}")
    return CommandResult(text="\n".join(lines))


async def cwd_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Display or change the working directory.

    Usage:
        /cwd             — show current directory
        /cwd /new/path   — change working directory
    """
    engine = context.get("engine")
    cwd = context.get("cwd", ".")

    if not args.strip():
        return CommandResult(text=f"Working directory: {cwd}")

    target = Path(args.strip()).expanduser().resolve()
    if not target.is_dir():
        return CommandResult(text=f"Not a directory: {target}")

    if engine is not None:
        engine.cwd = str(target)

    app_state = context.get("app_state")
    if app_state is not None:
        app_state.cwd = str(target)

    return CommandResult(text=f"Working directory changed to: {target}")
