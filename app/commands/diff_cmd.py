"""Diff command handler — show git diff in the working directory."""
from __future__ import annotations

import asyncio
from typing import Any

from app.command_registry import CommandResult


async def diff_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Show git diff output for the working directory.

    Usage:
        /diff               — show unstaged changes
        /diff --staged      — show staged changes
        /diff HEAD~3        — diff against specific ref
    """
    cwd = context.get("cwd", ".")
    git_args = args.strip() if args.strip() else ""
    command = f"git diff {git_args}".strip()

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        output = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")

        if proc.returncode != 0:
            return CommandResult(text=f"git diff failed:\n{err or output}")

        if not output.strip():
            return CommandResult(text="No changes detected.")

        return CommandResult(text=output)
    except FileNotFoundError:
        return CommandResult(text="Error: git is not installed or not in PATH.")
    except asyncio.TimeoutError:
        return CommandResult(text="git diff timed out.")
