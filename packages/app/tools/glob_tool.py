"""GlobTool — find files by name pattern."""
from __future__ import annotations
from pathlib import Path
from app.tool import BaseTool, ToolContext, ToolResult

MAX_RESULTS = 100

_PROMPT = """\
- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of \
globbing and grepping, use the Agent tool instead\
"""


class GlobTool(BaseTool):
    name = "Glob"

    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match files against",
            },
            "path": {
                "type": "string",
                "description": (
                    "The directory to search in. If not specified, the current working "
                    "directory will be used. IMPORTANT: Omit this field to use the default "
                    'directory. DO NOT enter "undefined" or "null" - simply omit it for '
                    "the default behavior. Must be a valid directory path if provided."
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
        base = Path(input.get("path", context.cwd))
        pattern = input["pattern"]
        try:
            matches = [p for p in base.glob(pattern) if p.is_file()]

            def safe_mtime(p: Path) -> float:
                try:
                    return p.stat().st_mtime
                except OSError:
                    return 0.0

            sorted_matches = sorted(matches, key=safe_mtime, reverse=True)
            paths = [str(p) for p in sorted_matches][:MAX_RESULTS]
            if not paths:
                return ToolResult(content="No files matched the pattern.")
            result = "\n".join(paths)
            if len(sorted_matches) > MAX_RESULTS:
                result += f"\n\n[Truncated: showing {MAX_RESULTS} of {len(sorted_matches)} matches]"
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)
