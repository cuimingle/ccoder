"""FileReadTool — read file contents with line range, PDF, and image support."""
from __future__ import annotations
from pathlib import Path
import base64
import mimetypes
from app.tool import BaseTool, ToolContext, ToolResult

MAX_LINES = 2000
PDF_MAX_PAGES_PER_READ = 20

_PROMPT = """\
Reads a file from the local filesystem. You can access any file directly by using this tool.
Assume this tool is able to read all files on the machine. If the User provides a path \
to a file assume that path is valid. It is okay to read a file that does not exist; \
an error will be returned.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 2000 lines starting from the beginning of the file
- When you already know which part of the file you need, only read that part. \
This can be important for larger files.
- Results are returned using cat -n format, with line numbers starting at 1
- This tool allows Claude Code to read images (eg PNG, JPG, etc). When reading an \
image file the contents are presented visually as Claude Code is a multimodal LLM.
- This tool can read PDF files (.pdf). For large PDFs (more than 10 pages), you MUST \
provide the pages parameter to read specific page ranges (e.g., pages: "1-5"). \
Reading a large PDF without the pages parameter will fail. Maximum 20 pages per request.
- This tool can read Jupyter notebooks (.ipynb files) and returns all cells with their \
outputs, combining code, text, and visualizations.
- This tool can only read files, not directories. To read a directory, use an ls command \
via the Bash tool.
- You will regularly be asked to read screenshots. If the user provides a path to a \
screenshot, ALWAYS use this tool to view the file at the path. This tool will work with \
all temporary file paths.
- If you read a file that exists but has empty contents you will receive a system reminder \
warning in place of file contents.\
"""


class FileReadTool(BaseTool):
    name = "Read"

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to read",
            },
            "offset": {
                "type": "integer",
                "description": (
                    "The line number to start reading from. Only provide if "
                    "the file is too large to read at once"
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "The number of lines to read. Only provide if the file "
                    "is too large to read at once."
                ),
            },
            "pages": {
                "type": "string",
                "description": (
                    f'Page range for PDF files (e.g., "1-5", "3", "10-20"). '
                    f"Only applicable to PDF files. Maximum {PDF_MAX_PAGES_PER_READ} "
                    f"pages per request."
                ),
            },
        },
        "required": ["file_path"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    def get_activity_description(self, input: dict | None = None) -> str | None:
        if input and "file_path" in input:
            return f"Reading {input['file_path']}"
        return None

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        file_path = input["file_path"]
        path = Path(file_path)

        if not path.exists():
            return ToolResult(content=f"File not found: {file_path}", is_error=True)
        if not path.is_file():
            return ToolResult(content=f"Not a file: {file_path}", is_error=True)

        # Track read state for Edit/Write validation
        if context.read_file_state is not None:
            context.read_file_state[file_path] = True

        suffix = path.suffix.lower()

        # Image files — return as base64 content block
        if suffix in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"):
            return self._read_image(path)

        # PDF files
        if suffix == ".pdf":
            return await self._read_pdf(path, input.get("pages"))

        # Jupyter notebooks
        if suffix == ".ipynb":
            return self._read_notebook(path)

        # Text files
        return self._read_text(path, input)

    def _read_text(self, path: Path, input: dict) -> ToolResult:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

        if not text:
            return ToolResult(
                content="<system-reminder>This file exists but has empty contents.</system-reminder>"
            )

        lines = text.splitlines(keepends=True)
        offset = max(0, int(input.get("offset", 1)) - 1)  # convert to 0-indexed
        limit = int(input.get("limit", MAX_LINES))
        selected = lines[offset : offset + limit]

        numbered = "".join(
            f"{offset + i + 1}\t{line}" for i, line in enumerate(selected)
        )
        return ToolResult(content=numbered)

    def _read_image(self, path: Path) -> ToolResult:
        try:
            data = path.read_bytes()
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            b64 = base64.b64encode(data).decode("ascii")
            return ToolResult(
                content=[
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": b64,
                        },
                    }
                ]
            )
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    async def _read_pdf(self, path: Path, pages: str | None) -> ToolResult:
        try:
            import importlib
            # Try pdfplumber first, then pymupdf
            pdf_mod = None
            for mod_name in ("pdfplumber", "fitz"):
                try:
                    pdf_mod = importlib.import_module(mod_name)
                    break
                except ImportError:
                    continue

            if pdf_mod is None:
                # Fallback: just report file info
                size = path.stat().st_size
                return ToolResult(
                    content=f"PDF file: {path.name} ({size} bytes). "
                    "Install pdfplumber or pymupdf for PDF reading support."
                )

            if hasattr(pdf_mod, "open"):  # pdfplumber
                with pdf_mod.open(str(path)) as pdf:
                    total_pages = len(pdf.pages)
                    start, end = self._parse_page_range(pages, total_pages)
                    if end - start > PDF_MAX_PAGES_PER_READ:
                        return ToolResult(
                            content=f"Too many pages requested. Maximum {PDF_MAX_PAGES_PER_READ} per request.",
                            is_error=True,
                        )
                    text_parts = []
                    for i in range(start, end):
                        page_text = pdf.pages[i].extract_text() or ""
                        text_parts.append(f"--- Page {i+1} ---\n{page_text}")
                    return ToolResult(content="\n\n".join(text_parts))
            else:
                # pymupdf (fitz)
                doc = pdf_mod.open(str(path))
                total_pages = len(doc)
                start, end = self._parse_page_range(pages, total_pages)
                if end - start > PDF_MAX_PAGES_PER_READ:
                    return ToolResult(
                        content=f"Too many pages requested. Maximum {PDF_MAX_PAGES_PER_READ} per request.",
                        is_error=True,
                    )
                text_parts = []
                for i in range(start, end):
                    page_text = doc[i].get_text() or ""
                    text_parts.append(f"--- Page {i+1} ---\n{page_text}")
                doc.close()
                return ToolResult(content="\n\n".join(text_parts))
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def _parse_page_range(self, pages: str | None, total: int) -> tuple[int, int]:
        """Parse page range string, return (start, end) 0-indexed."""
        if pages is None:
            if total > 10:
                raise ValueError(
                    f"PDF has {total} pages. For large PDFs, provide the pages parameter "
                    f'(e.g., pages: "1-5"). Maximum {PDF_MAX_PAGES_PER_READ} pages per request.'
                )
            return 0, total
        pages = pages.strip()
        if "-" in pages:
            parts = pages.split("-", 1)
            start = max(0, int(parts[0]) - 1)
            end = min(total, int(parts[1]))
        else:
            start = max(0, int(pages) - 1)
            end = min(total, start + 1)
        return start, end

    def _read_notebook(self, path: Path) -> ToolResult:
        import json
        try:
            nb = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult(content=f"Failed to parse notebook: {e}", is_error=True)

        cells = nb.get("cells", [])
        parts = []
        for i, cell in enumerate(cells):
            cell_type = cell.get("cell_type", "code")
            source = "".join(cell.get("source", []))
            parts.append(f"--- Cell {i} [{cell_type}] ---\n{source}")

            # Include outputs for code cells
            outputs = cell.get("outputs", [])
            for out in outputs:
                if "text" in out:
                    parts.append("Output:\n" + "".join(out["text"]))
                elif "data" in out:
                    for mime_type, data in out["data"].items():
                        if "text" in mime_type:
                            parts.append(f"Output ({mime_type}):\n" + "".join(data))

        return ToolResult(content="\n\n".join(parts) if parts else "Empty notebook.")
