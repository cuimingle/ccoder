"""Direct bash command execution for ! input mode."""
from __future__ import annotations

import asyncio

from app.command_registry import CommandResult

DEFAULT_TIMEOUT_S = 120.0


async def execute_bash(command: str, cwd: str) -> CommandResult:
    """Execute a shell command directly and return the output.

    Used by the ``!command`` input mode to bypass the Claude API.
    Reuses the subprocess pattern from BashTool.
    """
    if not command.strip():
        return CommandResult(text="No command provided.", handled=True)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=DEFAULT_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return CommandResult(
                text=f"Command timed out after {DEFAULT_TIMEOUT_S}s: {command}",
                handled=True,
            )

        output = stdout.decode(errors="replace")
        err_output = stderr.decode(errors="replace")
        combined = output
        if err_output:
            combined = (combined + err_output) if combined else err_output

        if proc.returncode != 0:
            header = f"Exit code {proc.returncode}"
            return CommandResult(text=f"{header}\n{combined}" if combined else header, handled=True)

        return CommandResult(text=combined or "(no output)", handled=True)
    except Exception as e:
        return CommandResult(text=f"Error: {e}", handled=True)
