"""FileEditTool — replace exact string in a file."""
from __future__ import annotations
from pathlib import Path
from app.tool import BaseTool, ToolContext, ToolResult

_PROMPT = """\
Performs exact string replacements in files.

Usage:
- You must use your `Read` tool at least once in the conversation before editing. \
This tool will error if you attempt an edit without reading the file.
- When editing text from Read tool output, ensure you preserve the exact indentation \
(tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format \
is: line number + tab. Everything after that is the actual file content to match. Never \
include any part of the line number prefix in the old_string or new_string.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless \
explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files \
unless asked.
- The edit will FAIL if `old_string` is not unique in the file. Either provide a larger \
string with more surrounding context to make it unique or use `replace_all` to change \
every instance of `old_string`.
- Use `replace_all` for replacing and renaming strings across the file. This parameter \
is useful if you want to rename a variable for instance.\
"""


class FileEditTool(BaseTool):
    name = "Edit"

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to modify",
            },
            "old_string": {
                "type": "string",
                "description": "The text to replace",
            },
            "new_string": {
                "type": "string",
                "description": "The text to replace it with (must be different from old_string)",
            },
            "replace_all": {
                "type": "boolean",
                "default": False,
                "description": "Replace all occurrences of old_string (default false)",
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    def get_activity_description(self, input: dict | None = None) -> str | None:
        if input and "file_path" in input:
            return f"Editing {input['file_path']}"
        return None

    async def validate_input(self, input: dict, context: ToolContext) -> dict:
        file_path = input.get("file_path", "")
        # Check read-before-edit requirement
        if context.read_file_state is not None:
            if file_path not in context.read_file_state:
                return {
                    "result": False,
                    "message": (
                        f"You must read the file with the Read tool before editing it. "
                        f"File not yet read: {file_path}"
                    ),
                }
        return {"result": True}

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        # Validate input first
        validation = await self.validate_input(input, context)
        if not validation["result"]:
            return ToolResult(content=validation["message"], is_error=True)

        path = Path(input["file_path"])
        if not path.exists():
            return ToolResult(
                content=f"File not found: {input['file_path']}", is_error=True
            )
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

        old_string = input["old_string"]
        new_string = input["new_string"]
        replace_all = input.get("replace_all", False)

        count = content.count(old_string)
        if count == 0:
            return ToolResult(
                content=f"String not found in file: {repr(old_string[:80])}",
                is_error=True,
            )
        if count > 1 and not replace_all:
            return ToolResult(
                content=f"Found {count} occurrences of the string. old_string must be unique, "
                "or use replace_all=true.",
                is_error=True,
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        path.write_text(new_content, encoding="utf-8")
        replaced = count if replace_all else 1
        return ToolResult(content=f"Replaced {replaced} occurrence(s) in {path.name}")
