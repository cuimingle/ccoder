"""Worktree tools — EnterWorktree and ExitWorktree."""
from __future__ import annotations
import asyncio
import re
import uuid
from pathlib import Path
from app.tool import BaseTool, ToolContext, ToolResult

_ENTER_WORKTREE_PROMPT = """\
Use this tool ONLY when the user explicitly asks to work in a worktree. This tool \
creates an isolated git worktree and switches the current session into it.

## When to Use

- The user explicitly says "worktree" (e.g., "start a worktree", "work in a worktree", \
"create a worktree", "use a worktree")

## When NOT to Use

- The user asks to create a branch, switch branches, or work on a different branch \
\u2014 use git commands instead
- The user asks to fix a bug or work on a feature \u2014 use normal git workflow \
unless they specifically mention worktrees
- Never use this tool unless the user explicitly mentions "worktree"

## Requirements

- Must be in a git repository
- Must not already be in a worktree

## Behavior

- Creates a new git worktree inside `.claude/worktrees/` with a new branch based on HEAD
- Switches the session's working directory to the new worktree
- Use ExitWorktree to leave the worktree mid-session (keep or remove). On session exit, \
if still in the worktree, the user will be prompted to keep or remove it

## Parameters

- `name` (optional): A name for the worktree. If not provided, a random name is generated.\
"""


def _validate_worktree_slug(name: str) -> None:
    """Validate worktree name: alphanumeric, dots, underscores, dashes; max 64 chars."""
    if len(name) > 64:
        raise ValueError(f"Worktree name too long (max 64 chars): {name}")
    if not re.match(r'^[a-zA-Z0-9._/-]+$', name):
        raise ValueError(
            f"Invalid worktree name: {name}. "
            "Use only letters, digits, dots, underscores, and dashes."
        )


class EnterWorktreeTool(BaseTool):
    name = "EnterWorktree"
    search_hint = "create isolated git worktree session"

    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Optional name for the worktree. Each segment may contain only "
                    "letters, digits, dots, underscores, and dashes; max 64 chars total. "
                    "A random name is generated if not provided."
                ),
            },
        },
    }

    async def prompt(self) -> str:
        return _ENTER_WORKTREE_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        name = input_data.get("name", uuid.uuid4().hex[:8])

        try:
            _validate_worktree_slug(name)
        except ValueError as e:
            return ToolResult(content=str(e), is_error=True)

        cwd = Path(context.cwd)

        # Check if we're in a git repo
        git_dir = cwd / ".git"
        if not git_dir.exists():
            return ToolResult(
                content="Not in a git repository. EnterWorktree requires a git repo.",
                is_error=True,
            )

        worktree_base = cwd / ".claude" / "worktrees"
        worktree_path = worktree_base / name
        branch_name = f"worktree-{name}"

        if worktree_path.exists():
            return ToolResult(
                content=f"Worktree '{name}' already exists at {worktree_path}",
                is_error=True,
            )

        try:
            worktree_base.mkdir(parents=True, exist_ok=True)
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "add", str(worktree_path), "-b", branch_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                error = stderr.decode(errors="replace").strip()
                return ToolResult(
                    content=f"Failed to create worktree: {error}", is_error=True
                )

            return ToolResult(
                content=f"Created worktree at {worktree_path} on branch {branch_name}. "
                f"Session working directory switched to the worktree."
            )
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)


# ──────────────────────────────────────────────────────────────────────
# ExitWorktree
# ──────────────────────────────────────────────────────────────────────

_EXIT_WORKTREE_PROMPT = """\
Exit a worktree session created by EnterWorktree and return the session to the \
original working directory.

## Scope

This tool ONLY operates on worktrees created by EnterWorktree in this session. \
It will NOT touch:
- Worktrees you created manually with `git worktree add`
- Worktrees from a previous session (even if created by EnterWorktree then)
- The directory you're in if EnterWorktree was never called

If called outside an EnterWorktree session, the tool is a **no-op**: it reports that \
no worktree session is active and takes no action. Filesystem state is unchanged.

## When to Use

- The user explicitly asks to "exit the worktree", "leave the worktree", "go back", \
or otherwise end the worktree session
- Do NOT call this proactively \u2014 only when the user asks

## Parameters

- `action` (required): `"keep"` or `"remove"`
  - `"keep"` \u2014 leave the worktree directory and branch intact on disk. Use this \
if the user wants to come back to the work later, or if there are changes to preserve.
  - `"remove"` \u2014 delete the worktree directory and its branch. Use this for a \
clean exit when the work is done or abandoned.
- `discard_changes` (optional, default false): only meaningful with `action: "remove"`. \
If the worktree has uncommitted files or commits not on the original branch, the tool \
will REFUSE to remove it unless this is set to `true`. If the tool returns an error \
listing changes, confirm with the user before re-invoking with `discard_changes: true`.

## Behavior

- Restores the session's working directory to where it was before EnterWorktree
- Clears CWD-dependent caches (system prompt sections, memory files, plans directory) \
so the session state reflects the original directory
- Once exited, EnterWorktree can be called again to create a fresh worktree\
"""


class ExitWorktreeTool(BaseTool):
    name = "ExitWorktree"
    search_hint = "exit leave worktree session return original"

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["keep", "remove"],
                "description": (
                    '"keep" leaves the worktree and branch on disk; '
                    '"remove" deletes both.'
                ),
            },
            "discard_changes": {
                "type": "boolean",
                "description": (
                    'Required true when action is "remove" and the worktree has '
                    "uncommitted files or unmerged commits. The tool will refuse "
                    "and list them otherwise."
                ),
            },
        },
        "required": ["action"],
    }

    async def prompt(self) -> str:
        return _EXIT_WORKTREE_PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        action = input_data["action"]
        discard = input_data.get("discard_changes", False)

        cwd = Path(context.cwd)

        # Check if we're in a worktree
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--git-common-dir",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout, _ = await proc.communicate()
            git_common = stdout.decode().strip()

            proc2 = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--git-dir",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout2, _ = await proc2.communicate()
            git_dir = stdout2.decode().strip()

            if git_common == git_dir:
                return ToolResult(
                    content="No worktree session is active. Nothing to do."
                )
        except Exception:
            return ToolResult(
                content="Not in a git repository.", is_error=True
            )

        if action == "keep":
            return ToolResult(
                content=f"Exited worktree at {cwd}. Worktree and branch kept on disk."
            )

        elif action == "remove":
            if not discard:
                # Check for uncommitted changes
                proc = await asyncio.create_subprocess_exec(
                    "git", "status", "--porcelain",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd),
                )
                stdout, _ = await proc.communicate()
                changes = stdout.decode().strip()
                if changes:
                    return ToolResult(
                        content=f"Worktree has uncommitted changes:\n{changes}\n\n"
                        "Set discard_changes: true to remove anyway, or use "
                        'action: "keep" to preserve the worktree.',
                        is_error=True,
                    )

            # Remove worktree
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "worktree", "remove", "--force", str(cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    error = stderr.decode(errors="replace").strip()
                    return ToolResult(
                        content=f"Failed to remove worktree: {error}",
                        is_error=True,
                    )
                return ToolResult(
                    content=f"Worktree at {cwd} removed. Session returned to original directory."
                )
            except Exception as e:
                return ToolResult(content=str(e), is_error=True)
        else:
            return ToolResult(
                content=f"Invalid action: {action}. Use 'keep' or 'remove'.",
                is_error=True,
            )
