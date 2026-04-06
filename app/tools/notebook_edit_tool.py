"""NotebookEditTool — edit cells in a Jupyter notebook (.ipynb) file."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from app.tool import BaseTool, ToolContext, ToolResult

_PROMPT = """\
Completely replaces the contents of a specific cell in a Jupyter notebook (.ipynb file) \
with new source. Jupyter notebooks are interactive documents that combine code, text, \
and visualizations, commonly used for data analysis and scientific computing. The \
notebook_path parameter must be an absolute path, not a relative path. The cell_number \
is 0-indexed. Use edit_mode=insert to add a new cell at the index specified by \
cell_number. Use edit_mode=delete to delete the cell at the index specified by cell_number.\
"""


class NotebookEditTool(BaseTool):
    name = "NotebookEdit"

    input_schema = {
        "type": "object",
        "properties": {
            "notebook_path": {
                "type": "string",
                "description": (
                    "The absolute path to the Jupyter notebook file to edit "
                    "(must be absolute, not relative)"
                ),
            },
            "cell_id": {
                "type": "string",
                "description": (
                    "The ID of the cell to edit. When inserting a new cell, the new "
                    "cell will be inserted after the cell with this ID, or at the "
                    "beginning if not specified."
                ),
            },
            "new_source": {
                "type": "string",
                "description": "The new source for the cell",
            },
            "cell_type": {
                "type": "string",
                "enum": ["code", "markdown"],
                "description": (
                    "The type of the cell (code or markdown). If not specified, it "
                    "defaults to the current cell type. If using edit_mode=insert, "
                    "this is required."
                ),
            },
            "edit_mode": {
                "type": "string",
                "enum": ["replace", "insert", "delete"],
                "description": (
                    "The type of edit to make (replace, insert, delete). "
                    "Defaults to replace."
                ),
            },
        },
        "required": ["notebook_path", "new_source"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    def get_activity_description(self, input: dict | None = None) -> str | None:
        if input and "notebook_path" in input:
            return f"Editing notebook {input['notebook_path']}"
        return None

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        notebook_path = input_data.get("notebook_path", "")
        cell_id = input_data.get("cell_id")
        # Backwards compatibility: accept cell_number as fallback
        if cell_id is None and "cell_number" in input_data:
            cell_id = str(input_data["cell_number"])
        new_source = input_data.get("new_source", "")
        edit_mode = input_data.get("edit_mode", "replace")
        cell_type = input_data.get("cell_type", "code")

        path = Path(notebook_path)
        if not path.exists():
            return ToolResult(
                content=f"Notebook not found: {notebook_path}", is_error=True
            )
        if not path.is_file():
            return ToolResult(
                content=f"Not a file: {notebook_path}", is_error=True
            )

        try:
            nb = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult(content=f"Failed to parse notebook: {e}", is_error=True)

        cells = nb.get("cells", [])

        # Find cell by ID or fallback to index 0
        target_idx = None
        if cell_id is not None:
            for i, cell in enumerate(cells):
                if cell.get("id") == cell_id:
                    target_idx = i
                    break
            if target_idx is None:
                # Try as numeric index for backwards compatibility
                try:
                    numeric = int(cell_id)
                    if numeric < 0:
                        return ToolResult(
                            content=f"Cell number cannot be negative: {numeric}",
                            is_error=True,
                        )
                    target_idx = numeric
                except ValueError:
                    return ToolResult(
                        content=f"Cell with id '{cell_id}' not found in notebook.",
                        is_error=True,
                    )

        # Handle empty notebooks in insert mode
        if edit_mode == "insert" and len(cells) == 0:
            target_idx = -1
        elif target_idx is None:
            target_idx = 0

        # Validate index
        if target_idx != -1 and (target_idx < 0 or target_idx >= len(cells)):
            if len(cells) == 0:
                return ToolResult(
                    content="Notebook has no cells.", is_error=True
                )
            return ToolResult(
                content=f"Cell index {target_idx} out of range "
                f"(notebook has {len(cells)} cells, valid range: 0-{len(cells)-1})",
                is_error=True,
            )

        if edit_mode == "replace":
            source_lines = _text_to_source_lines(new_source)
            cells[target_idx]["source"] = source_lines

        elif edit_mode == "insert":
            new_cell = _make_cell(cell_type, new_source)
            if target_idx == -1:
                cells.insert(0, new_cell)
            else:
                cells.insert(target_idx + 1, new_cell)

        elif edit_mode == "delete":
            cells.pop(target_idx)

        else:
            return ToolResult(
                content=f"Unknown edit_mode: '{edit_mode}'. Must be 'replace', 'insert', or 'delete'",
                is_error=True,
            )

        nb["cells"] = cells
        try:
            path.write_text(json.dumps(nb, indent=2), encoding="utf-8")
        except Exception as e:
            return ToolResult(content=f"Failed to write notebook: {e}", is_error=True)

        cell_ref = cell_id or str(target_idx)
        return ToolResult(
            content=f"Notebook cell {cell_ref} updated successfully ({edit_mode})"
        )


def _text_to_source_lines(text: str) -> list[str]:
    """Convert text to notebook source line list."""
    if not text:
        return []
    return text.splitlines(keepends=True)


def _make_cell(cell_type: str, source: str) -> dict:
    """Create a new notebook cell dict."""
    new_id = str(uuid.uuid4())[:8]
    source_lines = _text_to_source_lines(source)

    if cell_type == "markdown":
        return {
            "cell_type": "markdown",
            "id": new_id,
            "source": source_lines,
            "metadata": {},
        }
    else:
        return {
            "cell_type": "code",
            "id": new_id,
            "source": source_lines,
            "metadata": {},
            "execution_count": None,
            "outputs": [],
        }
