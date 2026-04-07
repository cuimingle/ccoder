"""Info-related command handlers — /stats, /status, /doctor, /context, /usage."""
from __future__ import annotations

import platform
import shutil
import sys
from typing import Any

from app.command_registry import CommandResult
from app.commands.cost import INPUT_PRICE_PER_M, OUTPUT_PRICE_PER_M


async def stats_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Show extended session statistics.

    Usage:
        /stats
    """
    input_tokens = context.get("total_input_tokens", 0)
    output_tokens = context.get("total_output_tokens", 0)
    turn_count = context.get("turn_count", 0)

    input_cost = input_tokens * INPUT_PRICE_PER_M / 1_000_000
    output_cost = output_tokens * OUTPUT_PRICE_PER_M / 1_000_000
    total_cost = input_cost + output_cost

    avg_in = input_tokens // turn_count if turn_count else 0
    avg_out = output_tokens // turn_count if turn_count else 0

    engine = context.get("engine")
    msg_count = len(engine.messages) if engine else 0

    lines = [
        "Session Statistics",
        f"  Turns:              {turn_count}",
        f"  Messages:           {msg_count}",
        f"  Input tokens:       {input_tokens:,}",
        f"  Output tokens:      {output_tokens:,}",
        f"  Avg input/turn:     {avg_in:,}",
        f"  Avg output/turn:    {avg_out:,}",
        f"  Total cost:         ${total_cost:.4f}",
    ]
    return CommandResult(text="\n".join(lines))


async def status_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Show system status.

    Usage:
        /status
    """
    engine = context.get("engine")
    model = engine.model if engine else "unknown"
    cwd = context.get("cwd", ".")
    perm_mode = engine.permission_mode if engine else "unknown"
    tool_count = len(getattr(engine, "_tools", [])) if engine else 0

    lines = [
        "System Status",
        f"  Model:       {model}",
        f"  Mode:        {perm_mode}",
        f"  Tools:       {tool_count} loaded",
        f"  Python:      {sys.version.split()[0]}",
        f"  Platform:    {platform.system()} {platform.release()}",
        f"  CWD:         {cwd}",
    ]
    return CommandResult(text="\n".join(lines))


async def doctor_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Run diagnostic checks.

    Usage:
        /doctor
    """
    checks: list[str] = []

    # Python version
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)
    checks.append(f"  {'✓' if py_ok else '✗'} Python {py_ver} {'(OK)' if py_ok else '(need 3.11+)'}")

    # Git
    git_path = shutil.which("git")
    checks.append(f"  {'✓' if git_path else '✗'} git {'found' if git_path else 'NOT FOUND'}")

    # API key
    import os
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    engine = context.get("engine")
    if engine:
        client = getattr(engine, "_api_client", None)
        if client and getattr(client, "_api_key", None):
            has_key = True
    checks.append(f"  {'✓' if has_key else '✗'} API key {'configured' if has_key else 'NOT SET'}")

    # uv
    uv_path = shutil.which("uv")
    checks.append(f"  {'✓' if uv_path else '–'} uv {'found' if uv_path else 'not found (optional)'}")

    # Settings files
    from pathlib import Path
    user_settings = Path.home() / ".claude" / "settings.json"
    checks.append(
        f"  {'✓' if user_settings.exists() else '–'} "
        f"~/.claude/settings.json {'exists' if user_settings.exists() else 'not found'}"
    )

    cwd = context.get("cwd", ".")
    proj_settings = Path(cwd) / ".claude" / "settings.json"
    checks.append(
        f"  {'✓' if proj_settings.exists() else '–'} "
        f".claude/settings.json {'exists' if proj_settings.exists() else 'not found'}"
    )

    lines = ["Diagnostics:"] + checks
    return CommandResult(text="\n".join(lines))


async def context_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Show current context information.

    Usage:
        /context
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    msg_count = len(engine.messages)
    tool_count = len(getattr(engine, "_tools", []))
    in_tokens = engine.total_input_tokens
    out_tokens = engine.total_output_tokens

    # Check for CLAUDE.md files
    from pathlib import Path
    claude_files: list[str] = []
    cwd = context.get("cwd", ".")
    for candidate in [
        Path.home() / ".claude" / "CLAUDE.md",
        Path(cwd) / ".claude" / "CLAUDE.md",
        Path(cwd) / "CLAUDE.md",
    ]:
        if candidate.exists():
            claude_files.append(str(candidate))

    lines = [
        "Context Information",
        f"  Messages:       {msg_count}",
        f"  Tools loaded:   {tool_count}",
        f"  Input tokens:   {in_tokens:,}",
        f"  Output tokens:  {out_tokens:,}",
        f"  CLAUDE.md files: {len(claude_files)}",
    ]
    for cf in claude_files:
        lines.append(f"    - {cf}")

    return CommandResult(text="\n".join(lines))


async def usage_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Show API usage summary.

    Usage:
        /usage
    """
    input_tokens = context.get("total_input_tokens", 0)
    output_tokens = context.get("total_output_tokens", 0)

    input_cost = input_tokens * INPUT_PRICE_PER_M / 1_000_000
    output_cost = output_tokens * OUTPUT_PRICE_PER_M / 1_000_000
    total_cost = input_cost + output_cost

    lines = [
        "API Usage",
        f"  Input:   {input_tokens:>10,} tokens  ${input_cost:.4f}",
        f"  Output:  {output_tokens:>10,} tokens  ${output_cost:.4f}",
        f"  Total:   {input_tokens + output_tokens:>10,} tokens  ${total_cost:.4f}",
    ]
    return CommandResult(text="\n".join(lines))
