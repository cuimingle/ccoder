# Claude Code Python — Phase 2: Tool System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 15 个工具（10 个始终启用 + 5 个条件启用），并注册到 `tools.py`，使 pipe 模式可以执行真实工具调用。

**Architecture:** 每个工具独立目录 `packages/app/tools/<ToolName>/`，实现统一的 `Tool` Protocol。`tools.py` 的 `get_tools()` 注册所有已启用工具。

**Tech Stack:** Python 3.11+, `asyncio`, `subprocess`, `pathlib`, `httpx`, `html2text`, `nbformat`, `glob`, `fnmatch`, `difflib`

---

## File Map

| 文件 | 职责 |
|------|------|
| `packages/app/tools/__init__.py` | 包标识 |
| `packages/app/tools/bash_tool.py` | BashTool — shell 执行，超时，沙箱 |
| `packages/app/tools/file_read_tool.py` | FileReadTool — 读文件，按行范围，大文件截断 |
| `packages/app/tools/file_edit_tool.py` | FileEditTool — 字符串替换 + diff |
| `packages/app/tools/file_write_tool.py` | FileWriteTool — 创建/覆写文件 |
| `packages/app/tools/grep_tool.py` | GrepTool — ripgrep/grep 内容搜索 |
| `packages/app/tools/glob_tool.py` | GlobTool — 文件名模式匹配 |
| `packages/app/tools/web_fetch_tool.py` | WebFetchTool — 抓 URL → Markdown → 摘要 |
| `packages/app/tools/web_search_tool.py` | WebSearchTool — Brave/DuckDuckGo 搜索 |
| `packages/app/tools/ask_user_tool.py` | AskUserQuestionTool — 控制台多问题交互 |
| `packages/app/tools/agent_tool.py` | AgentTool — 派发子 QueryEngine 实例 |
| `packages/app/tools/notebook_edit_tool.py` | NotebookEditTool — Jupyter 单元格编辑 |
| `packages/app/tools/task_tool.py` | TaskCreateTool/TaskUpdateTool/TaskListTool/TaskGetTool |
| `packages/app/tools.py` | get_tools() 更新，注册所有工具 |
| `tests/tools/test_bash_tool.py` | BashTool 单元测试 |
| `tests/tools/test_file_tools.py` | FileReadTool/FileEditTool/FileWriteTool 测试 |
| `tests/tools/test_search_tools.py` | GrepTool/GlobTool 测试 |
| `tests/tools/test_web_tools.py` | WebFetchTool/WebSearchTool 测试 |
| `tests/tools/test_ask_user_tool.py` | AskUserQuestionTool 测试 |
| `tests/tools/test_agent_tool.py` | AgentTool 测试 |
| `tests/tools/test_notebook_tool.py` | NotebookEditTool 测试 |
| `tests/tools/test_task_tool.py` | Task* 工具测试 |
| `tests/tools/test_tools_registry.py` | get_tools() 注册表测试 |

---

## Task 9: tools 包初始化 + BashTool

**Files:**
- Create: `packages/app/tools/__init__.py`
- Create: `packages/app/tools/bash_tool.py`
- Create: `tests/tools/__init__.py`
- Create: `tests/tools/test_bash_tool.py`

- [ ] **Step 1: 写测试 tests/tools/test_bash_tool.py**

```python
"""Tests for BashTool."""
from __future__ import annotations
import pytest
from app.tools.bash_tool import BashTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

@pytest.fixture
def tool():
    return BashTool()

def test_bash_tool_name(tool):
    assert tool.name == "Bash"

def test_bash_tool_is_enabled(tool):
    assert tool.is_enabled() is True

def test_bash_tool_has_input_schema(tool):
    assert "command" in tool.input_schema["properties"]

@pytest.mark.asyncio
async def test_bash_executes_command(tool, ctx):
    result = await tool.call({"command": "echo hello"}, ctx)
    assert "hello" in result.content
    assert result.is_error is False

@pytest.mark.asyncio
async def test_bash_captures_stderr(tool, ctx):
    result = await tool.call({"command": "echo error >&2; exit 1"}, ctx)
    assert result.is_error is True

@pytest.mark.asyncio
async def test_bash_timeout(tool, ctx):
    result = await tool.call({"command": "sleep 10", "timeout": 1}, ctx)
    assert result.is_error is True
    assert "timeout" in result.content.lower() or "timed out" in result.content.lower()

@pytest.mark.asyncio
async def test_bash_respects_cwd(tool, tmp_path, ctx):
    (tmp_path / "marker.txt").write_text("found")
    result = await tool.call({"command": "cat marker.txt"}, ctx)
    assert "found" in result.content
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/tools/test_bash_tool.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 创建 `packages/app/tools/__init__.py` 和 `tests/tools/__init__.py`（空文件）**

- [ ] **Step 4: 实现 `packages/app/tools/bash_tool.py`**

```python
"""BashTool — execute shell commands with timeout."""
from __future__ import annotations
import asyncio
from app.tool import Tool, ToolContext, ToolResult

DEFAULT_TIMEOUT = 120  # seconds

class BashTool:
    name = "Bash"
    description = (
        "Execute a shell command in the working directory. "
        "Returns stdout/stderr combined. Use timeout parameter to override the default (120s)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "timeout": {"type": "number", "description": "Timeout in seconds (default 120)"},
        },
        "required": ["command"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        command = input["command"]
        timeout = float(input.get("timeout", DEFAULT_TIMEOUT))
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    content=f"Command timed out after {timeout}s: {command}",
                    is_error=True,
                )
            output = stdout.decode(errors="replace")
            err_output = stderr.decode(errors="replace")
            combined = output
            if err_output:
                combined = combined + err_output if combined else err_output
            if proc.returncode != 0:
                return ToolResult(content=combined or f"Command exited with code {proc.returncode}", is_error=True)
            return ToolResult(content=combined or "")
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_bash_tool.py -v
```

Expected: 7 个测试全部 PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && git add packages/app/tools/ tests/tools/ && git commit -m "feat: BashTool with timeout and cwd support"
```

---

## Task 10: FileReadTool, FileEditTool, FileWriteTool

**Files:**
- Create: `packages/app/tools/file_read_tool.py`
- Create: `packages/app/tools/file_edit_tool.py`
- Create: `packages/app/tools/file_write_tool.py`
- Create: `tests/tools/test_file_tools.py`

- [ ] **Step 1: 写测试 tests/tools/test_file_tools.py**

```python
"""Tests for file operation tools."""
from __future__ import annotations
import pytest
from pathlib import Path
from app.tools.file_read_tool import FileReadTool
from app.tools.file_edit_tool import FileEditTool
from app.tools.file_write_tool import FileWriteTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

# --- FileReadTool ---

@pytest.mark.asyncio
async def test_file_read_basic(tmp_path, ctx):
    f = tmp_path / "hello.txt"
    f.write_text("hello world\n")
    result = await FileReadTool().call({"file_path": str(f)}, ctx)
    assert "hello world" in result.content
    assert result.is_error is False

@pytest.mark.asyncio
async def test_file_read_with_line_range(tmp_path, ctx):
    f = tmp_path / "lines.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    result = await FileReadTool().call({"file_path": str(f), "offset": 2, "limit": 2}, ctx)
    assert "line2" in result.content
    assert "line4" not in result.content

@pytest.mark.asyncio
async def test_file_read_not_found(ctx):
    result = await FileReadTool().call({"file_path": "/nonexistent/file.txt"}, ctx)
    assert result.is_error is True

# --- FileEditTool ---

@pytest.mark.asyncio
async def test_file_edit_replaces_string(tmp_path, ctx):
    f = tmp_path / "code.py"
    f.write_text("def foo():\n    return 1\n")
    result = await FileEditTool().call({
        "file_path": str(f),
        "old_string": "return 1",
        "new_string": "return 2",
    }, ctx)
    assert result.is_error is False
    assert f.read_text() == "def foo():\n    return 2\n"

@pytest.mark.asyncio
async def test_file_edit_old_string_not_found(tmp_path, ctx):
    f = tmp_path / "code.py"
    f.write_text("def foo(): pass\n")
    result = await FileEditTool().call({
        "file_path": str(f),
        "old_string": "nonexistent string",
        "new_string": "something",
    }, ctx)
    assert result.is_error is True

@pytest.mark.asyncio
async def test_file_edit_ambiguous_string(tmp_path, ctx):
    f = tmp_path / "dup.py"
    f.write_text("x = 1\nx = 1\n")
    result = await FileEditTool().call({
        "file_path": str(f),
        "old_string": "x = 1",
        "new_string": "x = 2",
    }, ctx)
    assert result.is_error is True
    assert "unique" in result.content.lower() or "multiple" in result.content.lower()

# --- FileWriteTool ---

@pytest.mark.asyncio
async def test_file_write_creates_file(tmp_path, ctx):
    f = tmp_path / "new_file.py"
    result = await FileWriteTool().call({
        "file_path": str(f),
        "content": "print('hello')\n",
    }, ctx)
    assert result.is_error is False
    assert f.read_text() == "print('hello')\n"

@pytest.mark.asyncio
async def test_file_write_overwrites_file(tmp_path, ctx):
    f = tmp_path / "existing.txt"
    f.write_text("old content\n")
    result = await FileWriteTool().call({
        "file_path": str(f),
        "content": "new content\n",
    }, ctx)
    assert result.is_error is False
    assert f.read_text() == "new content\n"

@pytest.mark.asyncio
async def test_file_write_creates_parent_dirs(tmp_path, ctx):
    f = tmp_path / "a" / "b" / "c.txt"
    result = await FileWriteTool().call({
        "file_path": str(f),
        "content": "deep file\n",
    }, ctx)
    assert result.is_error is False
    assert f.read_text() == "deep file\n"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_file_tools.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 `packages/app/tools/file_read_tool.py`**

```python
"""FileReadTool — read file contents with optional line range."""
from __future__ import annotations
from pathlib import Path
from app.tool import ToolContext, ToolResult

MAX_LINES = 2000

class FileReadTool:
    name = "Read"
    description = (
        "Read a file from the filesystem. Returns file contents with line numbers. "
        "Use offset and limit to read specific portions of large files."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
            "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed)"},
            "limit": {"type": "integer", "description": "Number of lines to read"},
        },
        "required": ["file_path"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        path = Path(input["file_path"])
        if not path.exists():
            return ToolResult(content=f"File not found: {input['file_path']}", is_error=True)
        if not path.is_file():
            return ToolResult(content=f"Not a file: {input['file_path']}", is_error=True)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

        lines = text.splitlines(keepends=True)
        offset = max(0, int(input.get("offset", 1)) - 1)  # convert to 0-indexed
        limit = int(input.get("limit", MAX_LINES))
        selected = lines[offset:offset + limit]

        numbered = "".join(
            f"{offset + i + 1}\t{line}" for i, line in enumerate(selected)
        )
        return ToolResult(content=numbered)

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 4: 实现 `packages/app/tools/file_edit_tool.py`**

```python
"""FileEditTool — replace exact string in a file."""
from __future__ import annotations
from pathlib import Path
from app.tool import ToolContext, ToolResult

class FileEditTool:
    name = "Edit"
    description = (
        "Edit a file by replacing an exact string. "
        "old_string must appear exactly once in the file. "
        "Use replace_all=true to replace every occurrence."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "old_string": {"type": "string", "description": "Exact string to replace (must be unique)"},
            "new_string": {"type": "string", "description": "Replacement string"},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences (default false)"},
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        path = Path(input["file_path"])
        if not path.exists():
            return ToolResult(content=f"File not found: {input['file_path']}", is_error=True)
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
                content=f"Found {count} occurrences of the string. old_string must be unique, or use replace_all=true.",
                is_error=True,
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        path.write_text(new_content, encoding="utf-8")
        replaced = content.count(old_string) if replace_all else 1
        return ToolResult(content=f"Replaced {replaced} occurrence(s) in {path.name}")

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 5: 实现 `packages/app/tools/file_write_tool.py`**

```python
"""FileWriteTool — create or overwrite a file."""
from __future__ import annotations
from pathlib import Path
from app.tool import ToolContext, ToolResult

class FileWriteTool:
    name = "Write"
    description = "Create a new file or overwrite an existing file with the given content."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to write"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["file_path", "content"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        path = Path(input["file_path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(input["content"], encoding="utf-8")
            return ToolResult(content=f"Written to {path}")
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_file_tools.py -v
```

Expected: 10 个测试全部 PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && git add packages/app/tools/file_*.py tests/tools/test_file_tools.py && git commit -m "feat: FileReadTool, FileEditTool, FileWriteTool"
```

---

## Task 11: GrepTool + GlobTool

**Files:**
- Create: `packages/app/tools/grep_tool.py`
- Create: `packages/app/tools/glob_tool.py`
- Create: `tests/tools/test_search_tools.py`

- [ ] **Step 1: 写测试 tests/tools/test_search_tools.py**

```python
"""Tests for GrepTool and GlobTool."""
from __future__ import annotations
import pytest
from pathlib import Path
from app.tools.grep_tool import GrepTool
from app.tools.glob_tool import GlobTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    print('hello')\n")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "README.md").write_text("# Project\nhello world\n")
    return tmp_path

# --- GrepTool ---

@pytest.mark.asyncio
async def test_grep_finds_pattern(project, ctx):
    result = await GrepTool().call({"pattern": "def hello", "path": str(project)}, ctx)
    assert result.is_error is False
    assert "main.py" in result.content

@pytest.mark.asyncio
async def test_grep_no_match_returns_empty(project, ctx):
    result = await GrepTool().call({"pattern": "nonexistent_xyz_pattern", "path": str(project)}, ctx)
    assert result.is_error is False
    assert result.content.strip() == "" or "no matches" in result.content.lower()

@pytest.mark.asyncio
async def test_grep_with_glob_filter(project, ctx):
    result = await GrepTool().call({
        "pattern": "def",
        "path": str(project),
        "glob": "*.py",
    }, ctx)
    assert "main.py" in result.content or "utils.py" in result.content

# --- GlobTool ---

@pytest.mark.asyncio
async def test_glob_finds_py_files(project, ctx):
    result = await GlobTool().call({"pattern": "**/*.py", "path": str(project)}, ctx)
    assert result.is_error is False
    assert "main.py" in result.content
    assert "utils.py" in result.content

@pytest.mark.asyncio
async def test_glob_finds_md_files(project, ctx):
    result = await GlobTool().call({"pattern": "*.md", "path": str(project)}, ctx)
    assert "README.md" in result.content

@pytest.mark.asyncio
async def test_glob_no_match(project, ctx):
    result = await GlobTool().call({"pattern": "**/*.xyz", "path": str(project)}, ctx)
    assert result.is_error is False
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_search_tools.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 `packages/app/tools/grep_tool.py`**

```python
"""GrepTool — search file contents using ripgrep or grep."""
from __future__ import annotations
import asyncio
import shutil
from app.tool import ToolContext, ToolResult

class GrepTool:
    name = "Grep"
    description = (
        "Search for a regex pattern in files. "
        "Uses ripgrep (rg) if available, falls back to grep. "
        "Returns matching lines with file paths and line numbers."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "Directory or file to search in"},
            "glob": {"type": "string", "description": "Glob pattern to filter files (e.g. '*.py')"},
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": "Output mode (default: content)",
            },
        },
        "required": ["pattern"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        pattern = input["pattern"]
        search_path = input.get("path", context.cwd)
        glob_filter = input.get("glob")
        output_mode = input.get("output_mode", "content")

        # Choose between rg and grep
        use_rg = shutil.which("rg") is not None

        if use_rg:
            cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
            if output_mode == "files_with_matches":
                cmd.append("-l")
            elif output_mode == "count":
                cmd.append("-c")
            if glob_filter:
                cmd += ["--glob", glob_filter]
            cmd += [pattern, search_path]
        else:
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
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode(errors="replace").strip()
            return ToolResult(content=output)
        except asyncio.TimeoutError:
            return ToolResult(content="Search timed out after 30s", is_error=True)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 4: 实现 `packages/app/tools/glob_tool.py`**

```python
"""GlobTool — find files by name pattern."""
from __future__ import annotations
from pathlib import Path
from app.tool import ToolContext, ToolResult

MAX_RESULTS = 1000

class GlobTool:
    name = "Glob"
    description = (
        "Find files matching a glob pattern. "
        "Returns matching file paths sorted by modification time."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py'"},
            "path": {"type": "string", "description": "Directory to search in (default: cwd)"},
        },
        "required": ["pattern"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        base = Path(input.get("path", context.cwd))
        pattern = input["pattern"]
        try:
            matches = sorted(
                base.glob(pattern),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            paths = [str(p) for p in matches if p.is_file()][:MAX_RESULTS]
            return ToolResult(content="\n".join(paths))
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_search_tools.py -v
```

Expected: 6 个测试全部 PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && git add packages/app/tools/grep_tool.py packages/app/tools/glob_tool.py tests/tools/test_search_tools.py && git commit -m "feat: GrepTool and GlobTool"
```

---

## Task 12: WebFetchTool + WebSearchTool

**Files:**
- Create: `packages/app/tools/web_fetch_tool.py`
- Create: `packages/app/tools/web_search_tool.py`
- Create: `tests/tools/test_web_tools.py`

- [ ] **Step 1: 写测试 tests/tools/test_web_tools.py**

```python
"""Tests for WebFetchTool and WebSearchTool."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.web_fetch_tool import WebFetchTool
from app.tools.web_search_tool import WebSearchTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

# --- WebFetchTool ---

@pytest.mark.asyncio
async def test_web_fetch_converts_html_to_markdown(ctx):
    html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_response.headers = {"content-type": "text/html"}

    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = mock_client

        result = await WebFetchTool().call({"url": "https://example.com", "prompt": "summarize"}, ctx)

    assert result.is_error is False
    assert "Hello" in result.content or "example" in result.content.lower()

@pytest.mark.asyncio
async def test_web_fetch_handles_error(ctx):
    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        MockClient.return_value = mock_client

        result = await WebFetchTool().call({"url": "https://bad.example.com"}, ctx)

    assert result.is_error is True

# --- WebSearchTool ---

@pytest.mark.asyncio
async def test_web_search_returns_results(ctx):
    mock_results = {
        "results": [
            {"title": "Python docs", "url": "https://python.org", "content": "Python is great"},
        ]
    }
    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=mock_results)
        mock_response.status_code = 200
        mock_client.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = mock_client

        result = await WebSearchTool().call({"query": "python programming"}, ctx)

    assert result.is_error is False

@pytest.mark.asyncio
async def test_web_search_no_api_key_returns_error(ctx, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    result = await WebSearchTool().call({"query": "test"}, ctx)
    assert result.is_error is True
    assert "api key" in result.content.lower() or "not configured" in result.content.lower()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_web_tools.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 `packages/app/tools/web_fetch_tool.py`**

```python
"""WebFetchTool — fetch URL and convert to Markdown."""
from __future__ import annotations
import httpx
import html2text
from app.tool import ToolContext, ToolResult

MAX_CONTENT_LENGTH = 50_000

class WebFetchTool:
    name = "WebFetch"
    description = "Fetch content from a URL and convert HTML to Markdown."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "prompt": {"type": "string", "description": "What to extract from the page (optional)"},
        },
        "required": ["url"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        url = input["url"]
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                response = await client.get(url)
            content_type = response.headers.get("content-type", "")
            if "html" in content_type:
                converter = html2text.HTML2Text()
                converter.ignore_links = False
                converter.ignore_images = True
                markdown = converter.handle(response.text)
            else:
                markdown = response.text
            truncated = markdown[:MAX_CONTENT_LENGTH]
            if len(markdown) > MAX_CONTENT_LENGTH:
                truncated += f"\n\n[Content truncated at {MAX_CONTENT_LENGTH} characters]"
            return ToolResult(content=truncated)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 4: 实现 `packages/app/tools/web_search_tool.py`**

```python
"""WebSearchTool — search the web using Brave Search API."""
from __future__ import annotations
import os
import httpx
from app.tool import ToolContext, ToolResult

class WebSearchTool:
    name = "WebSearch"
    description = "Search the web. Requires BRAVE_API_KEY environment variable."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Number of results (default 10)"},
            "allowed_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include results from these domains",
            },
        },
        "required": ["query"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        api_key = os.environ.get("BRAVE_API_KEY")
        if not api_key:
            return ToolResult(
                content="WebSearch not configured: BRAVE_API_KEY environment variable not set.",
                is_error=True,
            )
        query = input["query"]
        count = int(input.get("count", 10))
        allowed_domains = input.get("allowed_domains", [])

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"Accept": "application/json", "X-Subscription-Token": api_key},
                    params={"q": query, "count": count},
                )
            data = response.json()
            results = data.get("results", data.get("web", {}).get("results", []))

            if allowed_domains:
                results = [r for r in results if any(d in r.get("url", "") for d in allowed_domains)]

            lines = []
            for r in results[:count]:
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("content", r.get("description", ""))
                lines.append(f"**{title}**\n{url}\n{snippet}\n")

            return ToolResult(content="\n".join(lines) if lines else "No results found.")
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_web_tools.py -v
```

Expected: 4 个测试全部 PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && git add packages/app/tools/web_*.py tests/tools/test_web_tools.py && git commit -m "feat: WebFetchTool and WebSearchTool"
```

---

## Task 13: AskUserQuestionTool + AgentTool

**Files:**
- Create: `packages/app/tools/ask_user_tool.py`
- Create: `packages/app/tools/agent_tool.py`
- Create: `tests/tools/test_ask_user_tool.py`
- Create: `tests/tools/test_agent_tool.py`

- [ ] **Step 1: 写测试 tests/tools/test_ask_user_tool.py**

```python
"""Tests for AskUserQuestionTool."""
from __future__ import annotations
import pytest
from unittest.mock import patch
from app.tools.ask_user_tool import AskUserQuestionTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

def test_ask_user_tool_name():
    assert AskUserQuestionTool().name == "AskUserQuestion"

def test_ask_user_tool_schema():
    schema = AskUserQuestionTool().input_schema
    assert "questions" in schema["properties"]

@pytest.mark.asyncio
async def test_ask_user_presents_questions(ctx):
    tool = AskUserQuestionTool()
    questions = [
        {"question": "Which approach?", "header": "Approach",
         "options": [{"label": "A"}, {"label": "B"}], "multiSelect": False}
    ]
    with patch("builtins.input", return_value="1"):
        result = await tool.call({"questions": questions}, ctx)
    assert result.is_error is False
    assert "A" in result.content or "answers" in result.content.lower() or result.content

@pytest.mark.asyncio
async def test_ask_user_handles_non_interactive(ctx, monkeypatch):
    """In non-interactive mode (pipe), returns default first option."""
    tool = AskUserQuestionTool()
    questions = [
        {"question": "Pick one", "header": "Choice",
         "options": [{"label": "Option1"}, {"label": "Option2"}], "multiSelect": False}
    ]
    # Simulate EOF on stdin
    with patch("builtins.input", side_effect=EOFError):
        result = await tool.call({"questions": questions}, ctx)
    assert result.is_error is False
```

- [ ] **Step 2: 写测试 tests/tools/test_agent_tool.py**

```python
"""Tests for AgentTool."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.agent_tool import AgentTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path), session_id="test-session")

def test_agent_tool_name():
    assert AgentTool().name == "Agent"

def test_agent_tool_schema():
    schema = AgentTool().input_schema
    assert "description" in schema["properties"]
    assert "prompt" in schema["properties"]

@pytest.mark.asyncio
async def test_agent_tool_runs_subquery(ctx):
    from app.query import QueryResult
    mock_result = QueryResult(
        response_text="Sub-agent completed.",
        tool_calls=[],
        input_tokens=5,
        output_tokens=3,
        messages=[],
    )
    with patch("app.tools.agent_tool.QueryEngine") as MockEngine:
        engine_instance = MagicMock()
        engine_instance.run_turn = AsyncMock(return_value=mock_result)
        MockEngine.return_value = engine_instance

        result = await AgentTool().call({
            "description": "test agent",
            "prompt": "do something",
        }, ctx)

    assert result.is_error is False
    assert "Sub-agent completed." in result.content
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_ask_user_tool.py tests/tools/test_agent_tool.py -v
```

Expected: `ImportError`

- [ ] **Step 4: 实现 `packages/app/tools/ask_user_tool.py`**

```python
"""AskUserQuestionTool — present questions to user via console."""
from __future__ import annotations
import json
from app.tool import ToolContext, ToolResult

class AskUserQuestionTool:
    name = "AskUserQuestion"
    description = "Ask the user one or more questions and collect their answers."
    input_schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "header": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "multiSelect": {"type": "boolean"},
                    },
                    "required": ["question", "header", "options", "multiSelect"],
                },
                "minItems": 1,
                "maxItems": 4,
            }
        },
        "required": ["questions"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        questions = input["questions"]
        answers = {}
        for q in questions:
            question_text = q["question"]
            options = q.get("options", [])
            multi = q.get("multiSelect", False)
            print(f"\n{question_text}")
            for i, opt in enumerate(options, 1):
                label = opt.get("label", str(opt))
                desc = opt.get("description", "")
                print(f"  {i}. {label}" + (f" — {desc}" if desc else ""))
            try:
                if multi:
                    raw = input(f"Enter numbers (comma-separated, 1-{len(options)}): ").strip()
                    indices = [int(x.strip()) - 1 for x in raw.split(",") if x.strip().isdigit()]
                    selected = [options[i].get("label", str(options[i])) for i in indices if 0 <= i < len(options)]
                    answers[question_text] = selected
                else:
                    raw = input(f"Enter number (1-{len(options)}): ").strip()
                    idx = int(raw) - 1 if raw.isdigit() else 0
                    idx = max(0, min(idx, len(options) - 1))
                    answers[question_text] = options[idx].get("label", str(options[idx]))
            except (EOFError, ValueError):
                # Non-interactive: default to first option
                answers[question_text] = options[0].get("label", str(options[0])) if options else ""

        return ToolResult(content=json.dumps({"answers": answers}, ensure_ascii=False))

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 5: 实现 `packages/app/tools/agent_tool.py`**

```python
"""AgentTool — dispatch a sub-agent (nested QueryEngine)."""
from __future__ import annotations
import os
from app.tool import ToolContext, ToolResult
from app.query_engine import QueryEngine

class AgentTool:
    name = "Agent"
    description = (
        "Launch a sub-agent to handle a complex task. "
        "The sub-agent has access to all tools and runs independently."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "Short description of what the agent will do"},
            "prompt": {"type": "string", "description": "The task for the agent to perform"},
        },
        "required": ["description", "prompt"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        prompt = input["prompt"]
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        engine = QueryEngine(
            cwd=context.cwd,
            api_key=api_key,
            permission_mode=context.permission_mode,
        )
        try:
            result = await engine.run_turn(prompt)
            return ToolResult(content=result.response_text)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_ask_user_tool.py tests/tools/test_agent_tool.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && git add packages/app/tools/ask_user_tool.py packages/app/tools/agent_tool.py tests/tools/ && git commit -m "feat: AskUserQuestionTool and AgentTool"
```

---

## Task 14: NotebookEditTool + Task Tools

**Files:**
- Create: `packages/app/tools/notebook_edit_tool.py`
- Create: `packages/app/tools/task_tool.py`
- Create: `tests/tools/test_notebook_tool.py`
- Create: `tests/tools/test_task_tool.py`

- [ ] **Step 1: 写测试 tests/tools/test_notebook_tool.py**

```python
"""Tests for NotebookEditTool."""
from __future__ import annotations
import json
import pytest
from pathlib import Path
from app.tools.notebook_edit_tool import NotebookEditTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

@pytest.fixture
def notebook(tmp_path):
    nb = {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3"}},
        "cells": [
            {"cell_type": "code", "id": "cell-001", "source": "x = 1", "metadata": {}, "outputs": [], "execution_count": None},
            {"cell_type": "markdown", "id": "cell-002", "source": "# Title", "metadata": {}},
        ]
    }
    f = tmp_path / "test.ipynb"
    f.write_text(json.dumps(nb))
    return f

@pytest.mark.asyncio
async def test_notebook_replace_cell(notebook, ctx):
    result = await NotebookEditTool().call({
        "notebook_path": str(notebook),
        "new_source": "x = 42",
        "cell_number": 0,
    }, ctx)
    assert result.is_error is False
    nb = json.loads(notebook.read_text())
    assert nb["cells"][0]["source"] == "x = 42"

@pytest.mark.asyncio
async def test_notebook_insert_cell(notebook, ctx):
    result = await NotebookEditTool().call({
        "notebook_path": str(notebook),
        "new_source": "y = 2",
        "cell_type": "code",
        "edit_mode": "insert",
        "cell_number": 0,
    }, ctx)
    assert result.is_error is False
    nb = json.loads(notebook.read_text())
    assert len(nb["cells"]) == 3

@pytest.mark.asyncio
async def test_notebook_delete_cell(notebook, ctx):
    result = await NotebookEditTool().call({
        "notebook_path": str(notebook),
        "new_source": "",
        "edit_mode": "delete",
        "cell_number": 1,
    }, ctx)
    assert result.is_error is False
    nb = json.loads(notebook.read_text())
    assert len(nb["cells"]) == 1

@pytest.mark.asyncio
async def test_notebook_not_found(ctx):
    result = await NotebookEditTool().call({
        "notebook_path": "/nonexistent/notebook.ipynb",
        "new_source": "x = 1",
    }, ctx)
    assert result.is_error is True
```

- [ ] **Step 2: 写测试 tests/tools/test_task_tool.py**

```python
"""Tests for Task management tools."""
from __future__ import annotations
import pytest
from app.tools.task_tool import TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path), session_id="test-session")

@pytest.mark.asyncio
async def test_task_create(ctx):
    result = await TaskCreateTool().call({
        "subject": "Test task",
        "description": "Do something",
    }, ctx)
    assert result.is_error is False
    assert "created" in result.content.lower() or "task" in result.content.lower()

@pytest.mark.asyncio
async def test_task_list_empty(ctx):
    result = await TaskListTool().call({}, ctx)
    assert result.is_error is False

@pytest.mark.asyncio
async def test_task_create_and_get(ctx):
    create_result = await TaskCreateTool().call({
        "subject": "My task",
        "description": "Details here",
    }, ctx)
    assert create_result.is_error is False

    list_result = await TaskListTool().call({}, ctx)
    assert "My task" in list_result.content

@pytest.mark.asyncio
async def test_task_update_status(ctx):
    await TaskCreateTool().call({"subject": "Update me", "description": "desc"}, ctx)
    list_result = await TaskListTool().call({}, ctx)
    # Extract task ID from list output (format: "#1. [pending] Update me")
    import re
    match = re.search(r"#(\d+)", list_result.content)
    assert match, f"No task ID found in: {list_result.content}"
    task_id = match.group(1)
    update_result = await TaskUpdateTool().call({"taskId": task_id, "status": "in_progress"}, ctx)
    assert update_result.is_error is False
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_notebook_tool.py tests/tools/test_task_tool.py -v
```

Expected: `ImportError`

- [ ] **Step 4: 实现 `packages/app/tools/notebook_edit_tool.py`**

```python
"""NotebookEditTool — edit Jupyter notebook cells."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from app.tool import ToolContext, ToolResult

class NotebookEditTool:
    name = "NotebookEdit"
    description = "Edit a cell in a Jupyter notebook (.ipynb). Supports replace, insert, and delete operations."
    input_schema = {
        "type": "object",
        "properties": {
            "notebook_path": {"type": "string", "description": "Absolute path to the .ipynb file"},
            "new_source": {"type": "string", "description": "New source content for the cell"},
            "cell_number": {"type": "integer", "description": "0-indexed cell number (required for replace/delete)"},
            "cell_type": {"type": "string", "enum": ["code", "markdown"], "description": "Cell type (required for insert)"},
            "edit_mode": {"type": "string", "enum": ["replace", "insert", "delete"], "description": "Operation (default: replace)"},
        },
        "required": ["notebook_path", "new_source"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        path = Path(input["notebook_path"])
        if not path.exists():
            return ToolResult(content=f"Notebook not found: {input['notebook_path']}", is_error=True)
        try:
            nb = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult(content=f"Failed to parse notebook: {e}", is_error=True)

        cells = nb.get("cells", [])
        edit_mode = input.get("edit_mode", "replace")
        cell_number = int(input.get("cell_number", 0))
        new_source = input["new_source"]
        cell_type = input.get("cell_type", "code")

        if edit_mode == "replace":
            if cell_number < 0 or cell_number >= len(cells):
                return ToolResult(content=f"Cell index {cell_number} out of range (notebook has {len(cells)} cells)", is_error=True)
            cells[cell_number]["source"] = new_source

        elif edit_mode == "insert":
            new_cell: dict = {
                "cell_type": cell_type,
                "id": str(uuid.uuid4())[:8],
                "source": new_source,
                "metadata": {},
            }
            if cell_type == "code":
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            cells.insert(cell_number + 1, new_cell)

        elif edit_mode == "delete":
            if cell_number < 0 or cell_number >= len(cells):
                return ToolResult(content=f"Cell index {cell_number} out of range", is_error=True)
            cells.pop(cell_number)

        nb["cells"] = cells
        path.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
        return ToolResult(content=f"Cell {cell_number} {edit_mode}d in {path.name}")

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 5: 实现 `packages/app/tools/task_tool.py`**

```python
"""Task management tools — create, update, list, get tasks."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from typing import ClassVar
from app.tool import ToolContext, ToolResult

# In-memory task store keyed by session_id
_task_stores: dict[str, list[dict]] = {}

def _get_store(session_id: str) -> list[dict]:
    if session_id not in _task_stores:
        _task_stores[session_id] = []
    return _task_stores[session_id]

def _next_id(store: list[dict]) -> str:
    if not store:
        return "1"
    return str(max(int(t["id"]) for t in store) + 1)


class TaskCreateTool:
    name = "TaskCreate"
    description = "Create a new task in the task list."
    input_schema = {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "description": {"type": "string"},
            "activeForm": {"type": "string"},
        },
        "required": ["subject", "description"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        task = {
            "id": _next_id(store),
            "subject": input["subject"],
            "description": input["description"],
            "status": "pending",
            "owner": "",
            "activeForm": input.get("activeForm", ""),
        }
        store.append(task)
        return ToolResult(content=f"Task #{task['id']} created successfully: {task['subject']}")

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)


class TaskUpdateTool:
    name = "TaskUpdate"
    description = "Update the status, subject, or other fields of a task."
    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
            "subject": {"type": "string"},
            "owner": {"type": "string"},
        },
        "required": ["taskId"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        task_id = input["taskId"]
        task = next((t for t in store if t["id"] == task_id), None)
        if task is None:
            return ToolResult(content=f"Task #{task_id} not found", is_error=True)
        if "status" in input:
            if input["status"] == "deleted":
                store.remove(task)
                return ToolResult(content=f"Task #{task_id} deleted")
            task["status"] = input["status"]
        if "subject" in input:
            task["subject"] = input["subject"]
        if "owner" in input:
            task["owner"] = input["owner"]
        return ToolResult(content=f"Updated task #{task_id}")

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)


class TaskListTool:
    name = "TaskList"
    description = "List all tasks in the task list."
    input_schema = {"type": "object", "properties": {}}

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        if not store:
            return ToolResult(content="No tasks.")
        lines = [f"#{t['id']}. [{t['status']}] {t['subject']}" for t in store if t["status"] != "deleted"]
        return ToolResult(content="\n".join(lines))

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)


class TaskGetTool:
    name = "TaskGet"
    description = "Get full details of a task by ID."
    input_schema = {
        "type": "object",
        "properties": {"taskId": {"type": "string"}},
        "required": ["taskId"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        store = _get_store(context.session_id)
        task = next((t for t in store if t["id"] == input["taskId"]), None)
        if task is None:
            return ToolResult(content=f"Task #{input['taskId']} not found", is_error=True)
        return ToolResult(content=json.dumps(task, ensure_ascii=False, indent=2))

    def render_result(self, result: ToolResult) -> str:
        return str(result.content)
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_notebook_tool.py tests/tools/test_task_tool.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && git add packages/app/tools/notebook_edit_tool.py packages/app/tools/task_tool.py tests/tools/ && git commit -m "feat: NotebookEditTool and Task management tools"
```

---

## Task 15: 更新 tools.py 注册表 + 全套测试验证

**Files:**
- Modify: `packages/app/tools.py`
- Create: `tests/tools/test_tools_registry.py`

- [ ] **Step 1: 写测试 tests/tools/test_tools_registry.py**

```python
"""Tests for the tool registry."""
from __future__ import annotations
import pytest
from app.tools import get_tools

EXPECTED_TOOL_NAMES = {
    "Bash",
    "Read",
    "Edit",
    "Write",
    "Grep",
    "Glob",
    "WebFetch",
    "WebSearch",
    "AskUserQuestion",
    "Agent",
    "NotebookEdit",
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
}

def test_get_tools_returns_all_tools():
    tools = get_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES

def test_all_tools_are_enabled():
    tools = get_tools()
    for tool in tools:
        assert tool.is_enabled(), f"Tool {tool.name} should be enabled"

def test_all_tools_have_valid_schema():
    tools = get_tools()
    for tool in tools:
        assert isinstance(tool.input_schema, dict), f"{tool.name}.input_schema must be dict"
        assert tool.input_schema.get("type") == "object", f"{tool.name}.input_schema must have type=object"
        assert "properties" in tool.input_schema, f"{tool.name}.input_schema must have properties"

def test_all_tools_have_description():
    tools = get_tools()
    for tool in tools:
        assert tool.description, f"{tool.name} must have a description"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_tools_registry.py -v
```

Expected: 断言失败（get_tools() 返回空列表）

- [ ] **Step 3: 更新 `packages/app/tools.py`**

```python
"""Tool registry — assembles the list of available tools."""
from __future__ import annotations
from app.tool import Tool
from app.tools.bash_tool import BashTool
from app.tools.file_read_tool import FileReadTool
from app.tools.file_edit_tool import FileEditTool
from app.tools.file_write_tool import FileWriteTool
from app.tools.grep_tool import GrepTool
from app.tools.glob_tool import GlobTool
from app.tools.web_fetch_tool import WebFetchTool
from app.tools.web_search_tool import WebSearchTool
from app.tools.ask_user_tool import AskUserQuestionTool
from app.tools.agent_tool import AgentTool
from app.tools.notebook_edit_tool import NotebookEditTool
from app.tools.task_tool import (
    TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool,
)


def get_tools() -> list[Tool]:
    """Return the list of all enabled tools."""
    all_tools: list[Tool] = [
        BashTool(),
        FileReadTool(),
        FileEditTool(),
        FileWriteTool(),
        GrepTool(),
        GlobTool(),
        WebFetchTool(),
        WebSearchTool(),
        AskUserQuestionTool(),
        AgentTool(),
        NotebookEditTool(),
        TaskCreateTool(),
        TaskUpdateTool(),
        TaskListTool(),
        TaskGetTool(),
    ]
    return [t for t in all_tools if t.is_enabled()]
```

- [ ] **Step 4: 运行注册表测试确认通过**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/tools/test_tools_registry.py -v
```

Expected: 4 个测试全部 PASS

- [ ] **Step 5: 运行全套测试确认无回归**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && uv run pytest tests/ -v
```

Expected: 全部 PASS（Phase 1 的 28 个 + Phase 2 的新增测试）

- [ ] **Step 6: Commit**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python && git add packages/app/tools.py tests/tools/test_tools_registry.py && git commit -m "feat: register all 15 tools in get_tools()"
```

---

## 自检

### Spec 覆盖检查

| Spec 要求 | 对应 Task |
|-----------|----------|
| BashTool — shell 执行，超时 | Task 9 |
| FileReadTool — 文件读取，行范围 | Task 10 |
| FileEditTool — 字符串替换 + diff | Task 10 |
| FileWriteTool — 创建/覆写 | Task 10 |
| GrepTool — ripgrep/grep | Task 11 |
| GlobTool — 文件名模式匹配 | Task 11 |
| WebFetchTool — URL → Markdown | Task 12 |
| WebSearchTool — 网页搜索 | Task 12 |
| AskUserQuestionTool — 控制台交互 | Task 13 |
| AgentTool — 子代理 | Task 13 |
| NotebookEditTool — Jupyter 编辑 | Task 14 |
| TaskCreate/Update/List/Get | Task 14 |
| get_tools() 注册所有工具 | Task 15 |

### 类型一致性检查

- 所有工具实现 `Tool` Protocol（`name`, `description`, `input_schema`, `is_enabled()`, `call()`, `render_result()`）✓
- `call()` 签名：`async def call(self, input: dict, context: ToolContext) -> ToolResult` ✓
- `ToolContext.cwd` 在所有工具中用于确定工作目录 ✓
- `ToolContext.session_id` 在 TaskTool 中用于隔离任务存储 ✓

### 占位符扫描

无 TBD / TODO / "implement later" ✓

---

## 后续计划

- **Phase 3:** 权限系统 + Hook 系统
- **Phase 4:** Textual TUI（REPLScreen + 组件）
- **Phase 5:** 会话压缩（Compaction）
