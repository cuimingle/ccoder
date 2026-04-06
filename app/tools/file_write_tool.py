"""FileWriteTool — create or overwrite a file."""
from __future__ import annotations
from pathlib import Path
from app.tool import BaseTool, ToolContext, ToolResult

_PROMPT = """\
Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- If this is an existing file, you MUST use the Read tool first to read the file's \
contents. This tool will fail if you did not read the file first.
- Prefer the Edit tool for modifying existing files — it only sends the diff. Only use \
this tool to create new files or for complete rewrites.
- NEVER create documentation files (*.md) or README files unless explicitly requested \
by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files \
unless asked.\
"""


class FileWriteTool(BaseTool):
    name = "Write"

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to write (must be absolute, not relative)",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    def get_activity_description(self, input: dict | None = None) -> str | None:
        if input and "file_path" in input:
            return f"Writing {input['file_path']}"
        return None

    async def validate_input(self, input: dict, context: ToolContext) -> dict:
        file_path = input.get("file_path", "")
        path = Path(file_path)
        # Check read-before-write for existing files
        if path.exists() and context.read_file_state is not None:
            if file_path not in context.read_file_state:
                return {
                    "result": False,
                    "message": (
                        f"You must read the file with the Read tool before overwriting it. "
                        f"File not yet read: {file_path}"
                    ),
                }
        return {"result": True}

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        validation = await self.validate_input(input, context)
        if not validation["result"]:
            return ToolResult(content=validation["message"], is_error=True)

        path = Path(input["file_path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(input["content"], encoding="utf-8")
            return ToolResult(content=f"Written to {path}")
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)
