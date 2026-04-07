"""Config-related command handlers — /permissions, /hooks, /config."""
from __future__ import annotations

import json
from typing import Any

from app.command_registry import CommandResult


async def permissions_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Display current permission rules.

    Usage:
        /permissions
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    checker = getattr(engine, "_permission_checker", None)
    if checker is None:
        return CommandResult(text="Permission checker not available.")

    settings = getattr(checker, "_settings", None)
    if settings is None:
        return CommandResult(text="Settings not available.")

    lines = ["Permission Rules:"]
    lines.append(f"\n  Mode: {engine.permission_mode}")

    if settings.permissions_allow:
        lines.append("\n  Allow rules:")
        for rule in settings.permissions_allow:
            lines.append(f"    {rule.tool}({rule.pattern})")
    else:
        lines.append("\n  Allow rules: (none)")

    if settings.permissions_deny:
        lines.append("\n  Deny rules:")
        for rule in settings.permissions_deny:
            lines.append(f"    {rule.tool}({rule.pattern})")
    else:
        lines.append("\n  Deny rules: (none)")

    return CommandResult(text="\n".join(lines))


async def hooks_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Display configured hooks.

    Usage:
        /hooks
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    runner = getattr(engine, "_hook_runner", None)
    if runner is None:
        return CommandResult(text="Hook runner not available.")

    hooks = getattr(runner, "_hooks", [])
    if not hooks:
        return CommandResult(text="No hooks configured.")

    lines = ["Configured Hooks:"]
    for h in hooks:
        lines.append(f"  [{h.event}] {h.matcher} → {h.command} (timeout: {h.timeout}s)")

    return CommandResult(text="\n".join(lines))


async def config_handler(args: str, context: dict[str, Any]) -> CommandResult:
    """Display current settings.

    Usage:
        /config
    """
    engine = context.get("engine")
    if engine is None:
        return CommandResult(text="Engine not available.")

    settings = getattr(engine, "_permission_checker", None)
    settings = getattr(settings, "_settings", None) if settings else None

    info: dict[str, Any] = {
        "model": engine.model,
        "cwd": engine.cwd,
        "permission_mode": engine.permission_mode,
        "tools_loaded": len(getattr(engine, "_tools", [])),
        "turn_count": engine.turn_count,
    }

    if settings:
        info["allow_rules"] = len(settings.permissions_allow)
        info["deny_rules"] = len(settings.permissions_deny)
        info["hooks"] = len(settings.hooks)

    formatted = json.dumps(info, indent=2, ensure_ascii=False)
    return CommandResult(text=f"Current Configuration:\n{formatted}")
