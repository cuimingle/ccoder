"""GrepTool — search file contents using ripgrep with full flag support."""
from __future__ import annotations
import asyncio
import shutil
from app.tool import BaseTool, ToolContext, ToolResult

DEFAULT_HEAD_LIMIT = 250

_PROMPT = """\
A powerful search tool built on ripgrep

  Usage:
  - ALWAYS use Grep for search tasks. NEVER invoke `grep` or `rg` as a Bash command. \
The Grep tool has been optimized for correct permissions and access.
  - Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
  - Filter files with glob parameter (e.g., "*.js", "**/*.tsx") or type parameter \
(e.g., "js", "py", "rust")
  - Output modes: "content" shows matching lines, "files_with_matches" shows only file \
paths (default), "count" shows match counts
  - Use Agent tool for open-ended searches requiring multiple rounds
  - Pattern syntax: Uses ripgrep (not grep) - literal braces need escaping \
(use `interface\\{\\}` to find `interface{}` in Go code)
  - Multiline matching: By default patterns match within single lines only. For \
cross-line patterns like `struct \\{[\\s\\S]*?field`, use `multiline: true`\
"""


class GrepTool(BaseTool):
    name = "Grep"

    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regular expression pattern to search for in file contents",
            },
            "path": {
                "type": "string",
                "description": (
                    "File or directory to search in (rg PATH). "
                    "Defaults to current working directory."
                ),
            },
            "glob": {
                "type": "string",
                "description": (
                    'Glob pattern to filter files (e.g. "*.js", "*.{ts,tsx}") '
                    "- maps to rg --glob"
                ),
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": (
                    'Output mode: "content" shows matching lines (supports -A/-B/-C '
                    "context, -n line numbers, head_limit), "
                    '"files_with_matches" shows file paths (supports head_limit), '
                    '"count" shows match counts (supports head_limit). '
                    'Defaults to "files_with_matches".'
                ),
            },
            "-B": {
                "type": "number",
                "description": (
                    "Number of lines to show before each match (rg -B). "
                    'Requires output_mode: "content", ignored otherwise.'
                ),
            },
            "-A": {
                "type": "number",
                "description": (
                    "Number of lines to show after each match (rg -A). "
                    'Requires output_mode: "content", ignored otherwise.'
                ),
            },
            "-C": {
                "type": "number",
                "description": "Alias for context.",
            },
            "context": {
                "type": "number",
                "description": (
                    "Number of lines to show before and after each match (rg -C). "
                    'Requires output_mode: "content", ignored otherwise.'
                ),
            },
            "-n": {
                "type": "boolean",
                "description": (
                    "Show line numbers in output (rg -n). "
                    'Requires output_mode: "content", ignored otherwise. Defaults to true.'
                ),
            },
            "-i": {
                "type": "boolean",
                "description": "Case insensitive search (rg -i)",
            },
            "type": {
                "type": "string",
                "description": (
                    "File type to search (rg --type). Common types: js, py, rust, go, "
                    "java, etc. More efficient than include for standard file types."
                ),
            },
            "head_limit": {
                "type": "number",
                "description": (
                    'Limit output to first N lines/entries, equivalent to "| head -N". '
                    "Works across all output modes: content (limits output lines), "
                    "files_with_matches (limits file paths), count (limits count entries). "
                    "Defaults to 250 when unspecified. Pass 0 for unlimited "
                    "(use sparingly \u2014 large result sets waste context)."
                ),
            },
            "offset": {
                "type": "number",
                "description": (
                    "Skip first N lines/entries before applying head_limit, "
                    'equivalent to "| tail -n +N | head -N". '
                    "Works across all output modes. Defaults to 0."
                ),
            },
            "multiline": {
                "type": "boolean",
                "description": (
                    "Enable multiline mode where . matches newlines and patterns can "
                    "span lines (rg -U --multiline-dotall). Default: false."
                ),
            },
        },
        "required": ["pattern"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        pattern = input["pattern"]
        search_path = input.get("path", context.cwd)
        glob_filter = input.get("glob")
        output_mode = input.get("output_mode", "files_with_matches")
        head_limit = int(input.get("head_limit", DEFAULT_HEAD_LIMIT))
        offset = int(input.get("offset", 0))
        multiline = input.get("multiline", False)
        case_insensitive = input.get("-i", False)
        show_line_numbers = input.get("-n", True)
        file_type = input.get("type")
        before_context = input.get("-B")
        after_context = input.get("-A")
        context_lines = input.get("-C") or input.get("context")

        use_rg = shutil.which("rg") is not None
        if not use_rg:
            return await self._grep_fallback(
                pattern, search_path, glob_filter, output_mode, context
            )

        cmd = ["rg", "--no-heading", "--color=never"]

        # Output mode
        if output_mode == "files_with_matches":
            cmd.append("-l")
        elif output_mode == "count":
            cmd.append("-c")
        else:
            # content mode
            if show_line_numbers:
                cmd.append("--line-number")

        # Context lines (only for content mode)
        if output_mode == "content":
            if context_lines is not None:
                cmd += ["-C", str(int(context_lines))]
            else:
                if before_context is not None:
                    cmd += ["-B", str(int(before_context))]
                if after_context is not None:
                    cmd += ["-A", str(int(after_context))]

        # Flags
        if case_insensitive:
            cmd.append("-i")
        if multiline:
            cmd += ["-U", "--multiline-dotall"]
        if glob_filter:
            cmd += ["--glob", glob_filter]
        if file_type:
            cmd += ["--type", file_type]

        cmd += [pattern, search_path]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(content="Search timed out after 30s", is_error=True)

            if proc.returncode not in (0, 1):
                error_msg = stderr.decode(errors="replace").strip()
                return ToolResult(content=error_msg, is_error=True)

            output = stdout.decode(errors="replace").strip()
            if not output:
                return ToolResult(content="No matches found.")

            # Apply offset and head_limit
            lines = output.split("\n")
            if offset > 0:
                lines = lines[offset:]
            if head_limit > 0:
                lines = lines[:head_limit]

            return ToolResult(content="\n".join(lines))
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    async def _grep_fallback(
        self,
        pattern: str,
        search_path: str,
        glob_filter: str | None,
        output_mode: str,
        context: ToolContext,
    ) -> ToolResult:
        """Fallback to grep when ripgrep is not available."""
        cmd = ["grep", "-rn", "--color=never"]
        if output_mode == "files_with_matches":
            cmd.append("-l")
        elif output_mode == "count":
            cmd.append("-c")
        if glob_filter:
            cmd += ["--include", glob_filter]
        cmd += [pattern, search_path]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(content="Search timed out after 30s", is_error=True)

            if proc.returncode in (0, 1):
                output = stdout.decode(errors="replace").strip()
                return ToolResult(content=output or "No matches found.")
            else:
                error_msg = stderr.decode(errors="replace").strip()
                return ToolResult(content=error_msg, is_error=True)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)
