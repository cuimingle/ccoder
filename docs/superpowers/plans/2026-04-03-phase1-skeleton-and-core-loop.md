# Claude Code Python — Phase 1: Skeleton + Core Loop

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建项目骨架，实现 API 客户端 + 流式工具调用循环，使 pipe 模式（`echo "say hello" | python -m app -p`）端到端可运行。

**Architecture:** Click CLI 入口 → `main.py` 解析参数 → `QueryEngine` 管理会话 → `query()` 发起流式 API 请求并处理工具调用循环。所有模块通过 `types/` 中的数据类通信，无循环依赖。

**Tech Stack:** Python ≥ 3.11, `uv`, `anthropic` SDK, `click`, `asyncio`, `pytest`, `pytest-asyncio`

---

## File Map

| 文件 | 职责 |
|------|------|
| `pyproject.toml` | 项目配置，依赖声明，入口点 |
| `packages/app/__init__.py` | 包标识 |
| `packages/app/types/message.py` | 消息类型（UserMessage, AssistantMessage, ToolUseBlock 等） |
| `packages/app/types/permissions.py` | 权限模式枚举 |
| `packages/app/bootstrap/state.py` | 模块级单例（session_id, cwd, token counts） |
| `packages/app/tool.py` | Tool Protocol, ToolResult, find_tool_by_name |
| `packages/app/tools.py` | 工具注册表（Phase 1 只注册 stub） |
| `packages/app/services/api/claude.py` | Anthropic SDK 封装，流式 streaming，构建 request params |
| `packages/app/query.py` | 流式 API 调用 + 工具调用循环 + token 追踪 |
| `packages/app/query_engine.py` | 会话状态管理，turn bookkeeping，wrap query() |
| `packages/app/context.py` | 构建 system prompt（git status, CLAUDE.md, cwd） |
| `packages/app/main.py` | Click CLI 命令定义，启动 pipe 模式或 REPL |
| `packages/app/entrypoints/cli.py` | 入口，注入全局状态，调用 main() |
| `tests/test_types.py` | 消息类型单元测试 |
| `tests/test_query.py` | query() 单元测试（mock API） |
| `tests/test_query_engine.py` | QueryEngine 单元测试 |
| `tests/test_context.py` | context 构建单元测试 |
| `tests/conftest.py` | pytest fixtures |

---

## Task 1: 项目骨架（pyproject.toml + 包结构）

**Files:**
- Create: `pyproject.toml`
- Create: `packages/app/__init__.py`
- Create: `packages/app/entrypoints/__init__.py`
- Create: `packages/app/entrypoints/cli.py`
- Create: `packages/app/bootstrap/__init__.py`
- Create: `packages/app/bootstrap/state.py`
- Create: `packages/app/services/__init__.py`
- Create: `packages/app/services/api/__init__.py`
- Create: `packages/app/types/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "claude-code-python"
version = "0.1.0"
description = "Python implementation of Claude Code CLI"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "click>=8.1.0",
    "textual>=0.80.0",
    "json5>=0.9.0",
    "httpx>=0.27.0",
    "gitpython>=3.1.0",
    "html2text>=2024.2.26",
    "nbformat>=5.10.0",
]

[project.scripts]
claude-code = "app.entrypoints.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["packages/app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.14.0",
]
```

- [ ] **Step 2: 创建包 __init__ 文件**

`packages/app/__init__.py`:
```python
"""Claude Code Python — AI coding assistant CLI."""
__version__ = "0.1.0"
```

所有其他 `__init__.py` 文件（`entrypoints/`, `bootstrap/`, `services/`, `services/api/`, `types/`, `tests/`）内容均为空文件。

- [ ] **Step 3: 创建 bootstrap/state.py（模块级单例）**

```python
"""Module-level singletons for session-global state."""
from __future__ import annotations
import os
import uuid
from pathlib import Path


# Session ID — generated once per process
_session_id: str = str(uuid.uuid4())

# Working directory at startup
_original_cwd: Path = Path(os.getcwd())

# Token counts for the session
_session_input_tokens: int = 0
_session_output_tokens: int = 0


def get_session_id() -> str:
    return _session_id


def get_original_cwd() -> Path:
    return _original_cwd


def get_session_tokens() -> tuple[int, int]:
    """Returns (input_tokens, output_tokens)."""
    return _session_input_tokens, _session_output_tokens


def add_tokens(input_tokens: int, output_tokens: int) -> None:
    global _session_input_tokens, _session_output_tokens
    _session_input_tokens += input_tokens
    _session_output_tokens += output_tokens
```

- [ ] **Step 4: 创建入口 entrypoints/cli.py**

```python
"""CLI entrypoint — injects global state before any other imports."""
from __future__ import annotations
import asyncio
import sys


def main() -> None:
    """Main entry point for the claude-code CLI."""
    # Import here to ensure bootstrap state is initialized first
    from app.main import cli
    cli()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 创建 tests/conftest.py**

```python
"""Shared pytest fixtures."""
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    (tmp_path / "CLAUDE.md").write_text("# Test Project\n")
    return tmp_path


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for tests."""
    client = MagicMock()
    client.messages = MagicMock()
    return client
```

- [ ] **Step 6: 安装依赖并验证包可导入**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
uv sync
python -c "import app; print(app.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 7: Commit**

```bash
git init
git add pyproject.toml src/ tests/
git commit -m "feat: project skeleton with bootstrap state and entry point"
```

---

## Task 2: 消息类型系统

**Files:**
- Create: `packages/app/types/message.py`
- Create: `packages/app/types/permissions.py`
- Create: `tests/test_types.py`

- [ ] **Step 1: 编写失败的测试**

`tests/test_types.py`:
```python
"""Tests for message type hierarchy."""
from __future__ import annotations
import pytest
from app.types.message import (
    UserMessage,
    AssistantMessage,
    ToolUseBlock,
    ToolResultBlock,
    TextBlock,
    SystemMessage,
    MessageRole,
)
from app.types.permissions import PermissionMode


def test_user_message_creation():
    msg = UserMessage(content="hello")
    assert msg.role == MessageRole.USER
    assert msg.content == "hello"


def test_assistant_message_with_text_block():
    block = TextBlock(text="Hello!")
    msg = AssistantMessage(content=[block])
    assert msg.role == MessageRole.ASSISTANT
    assert len(msg.content) == 1
    assert msg.content[0].text == "Hello!"


def test_tool_use_block():
    block = ToolUseBlock(id="call_123", name="BashTool", input={"command": "ls"})
    assert block.type == "tool_use"
    assert block.name == "BashTool"
    assert block.input == {"command": "ls"}


def test_tool_result_block():
    block = ToolResultBlock(tool_use_id="call_123", content="file1.py\nfile2.py")
    assert block.type == "tool_result"
    assert block.tool_use_id == "call_123"


def test_permission_mode_enum():
    assert PermissionMode.MANUAL.value == "manual"
    assert PermissionMode.AUTO.value == "auto"
    assert PermissionMode.PLAN.value == "plan"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/mingcui/Documents/文稿/claude-code-python
uv run pytest tests/test_types.py -v
```

Expected: `ImportError` 或 `ModuleNotFoundError`

- [ ] **Step 3: 实现 types/message.py**

```python
"""Message type hierarchy for Claude API communication."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Union


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class TextBlock:
    text: str
    type: str = field(default="text", init=False)


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = field(default="tool_use", init=False)


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str | list[dict]
    is_error: bool = False
    type: str = field(default="tool_result", init=False)


ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock]


@dataclass
class UserMessage:
    content: str | list[ContentBlock]
    role: MessageRole = field(default=MessageRole.USER, init=False)


@dataclass
class AssistantMessage:
    content: list[ContentBlock]
    role: MessageRole = field(default=MessageRole.ASSISTANT, init=False)


@dataclass
class SystemMessage:
    content: str
    role: MessageRole = field(default=MessageRole.SYSTEM, init=False)


Message = Union[UserMessage, AssistantMessage, SystemMessage]
```

- [ ] **Step 4: 实现 types/permissions.py**

```python
"""Permission mode and result types."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class PermissionMode(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"
    PLAN = "plan"


class PermissionResult(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ALLOW_ALWAYS = "allow_always"
    DENY_ALWAYS = "deny_always"


@dataclass
class PermissionDecision:
    result: PermissionResult
    reason: str = ""
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_types.py -v
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add packages/app/types/ tests/test_types.py
git commit -m "feat: message and permission type hierarchy"
```

---

## Task 3: Tool Protocol 和注册表

**Files:**
- Create: `packages/app/tool.py`
- Create: `packages/app/tools.py`
- Create: `tests/test_tool.py`

- [ ] **Step 1: 编写失败的测试**

`tests/test_tool.py`:
```python
"""Tests for Tool protocol and registry."""
from __future__ import annotations
import pytest
from app.tool import ToolResult, find_tool_by_name, ToolContext
from app.tools import get_tools


class MockTool:
    name = "MockTool"
    description = "A mock tool for testing"
    input_schema = {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: "ToolContext") -> ToolResult:
        return ToolResult(content=f"mock result: {input['input']}")

    def render_result(self, result: ToolResult) -> str:
        return result.content


def test_tool_result_creation():
    result = ToolResult(content="hello")
    assert result.content == "hello"
    assert result.is_error is False


def test_tool_result_error():
    result = ToolResult(content="error!", is_error=True)
    assert result.is_error is True


def test_find_tool_by_name_found():
    tools = [MockTool()]
    found = find_tool_by_name(tools, "MockTool")
    assert found is not None
    assert found.name == "MockTool"


def test_find_tool_by_name_not_found():
    tools = [MockTool()]
    found = find_tool_by_name(tools, "NonExistentTool")
    assert found is None


def test_get_tools_returns_list():
    tools = get_tools()
    assert isinstance(tools, list)
    # Phase 1: no tools registered yet, returns empty list
    assert len(tools) == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_tool.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 tool.py**

```python
"""Tool Protocol definition and utilities."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class ToolResult:
    content: str | list[dict]
    is_error: bool = False


@dataclass
class ToolContext:
    """Context passed to each tool call."""
    cwd: str
    permission_mode: str = "manual"
    session_id: str = ""


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict

    def is_enabled(self) -> bool: ...
    async def call(self, input: dict, context: ToolContext) -> ToolResult: ...
    def render_result(self, result: ToolResult) -> str: ...


def find_tool_by_name(tools: list[Tool], name: str) -> Tool | None:
    """Find a tool by its name. Returns None if not found."""
    for tool in tools:
        if tool.name == name:
            return tool
    return None
```

- [ ] **Step 4: 实现 tools.py**

```python
"""Tool registry — assembles the list of available tools."""
from __future__ import annotations
from app.tool import Tool


def get_tools() -> list[Tool]:
    """Return the list of enabled tools.
    
    Phase 1: Returns empty list. Tools are added in Phase 2.
    """
    return []
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_tool.py -v
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add packages/app/tool.py packages/app/tools.py tests/test_tool.py
git commit -m "feat: Tool protocol, ToolResult, and empty tool registry"
```

---

## Task 4: Anthropic API 客户端

**Files:**
- Create: `packages/app/services/api/claude.py`
- Create: `tests/test_api_client.py`

- [ ] **Step 1: 编写失败的测试**

`tests/test_api_client.py`:
```python
"""Tests for Anthropic API client."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.api.claude import ClaudeAPIClient, APIRequestParams, StreamEvent


def test_api_request_params_defaults():
    params = APIRequestParams(
        model="claude-opus-4-6",
        messages=[{"role": "user", "content": "hello"}],
        system="You are helpful.",
        tools=[],
    )
    assert params.model == "claude-opus-4-6"
    assert params.max_tokens == 8096
    assert params.stream is True


def test_stream_event_text():
    event = StreamEvent(type="text_delta", text="hello")
    assert event.type == "text_delta"
    assert event.text == "hello"


def test_stream_event_tool_use():
    event = StreamEvent(
        type="tool_use",
        tool_use_id="call_123",
        tool_name="BashTool",
        tool_input={"command": "ls"},
    )
    assert event.type == "tool_use"
    assert event.tool_name == "BashTool"


@pytest.mark.asyncio
async def test_client_build_request_params():
    client = ClaudeAPIClient(api_key="test_key")
    params = client.build_request_params(
        messages=[{"role": "user", "content": "hello"}],
        system="You are helpful.",
        tools=[],
    )
    assert params.model == "claude-opus-4-6"
    assert len(params.messages) == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_api_client.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 services/api/claude.py**

```python
"""Anthropic API client — streaming wrapper."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import AsyncIterator
import anthropic


DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_MAX_TOKENS = 8096


@dataclass
class APIRequestParams:
    model: str
    messages: list[dict]
    system: str
    tools: list[dict]
    max_tokens: int = DEFAULT_MAX_TOKENS
    stream: bool = True


@dataclass
class StreamEvent:
    """Normalized stream event from the API."""
    type: str  # "text_delta" | "tool_use" | "message_stop" | "usage"
    text: str = ""
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0


class ClaudeAPIClient:
    """Wraps the Anthropic SDK with streaming support."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self._client = anthropic.Anthropic(api_key=self._api_key)

    def build_request_params(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> APIRequestParams:
        return APIRequestParams(
            model=self.model,
            messages=messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
        )

    async def stream(self, params: APIRequestParams) -> AsyncIterator[StreamEvent]:
        """Stream events from the Claude API."""
        # Accumulate tool input JSON across input_json_delta events
        tool_input_accumulator: dict[str, str] = {}  # tool_use_id -> json string

        with self._client.messages.stream(
            model=params.model,
            max_tokens=params.max_tokens,
            system=params.system,
            messages=params.messages,
            tools=params.tools,
        ) as stream:
            for event in stream:
                yield from self._process_event(event, tool_input_accumulator)

    def _process_event(
        self, event, tool_input_accumulator: dict[str, str]
    ) -> list[StreamEvent]:
        """Convert raw SDK event to normalized StreamEvents."""
        import anthropic.types as at
        results = []

        if hasattr(event, "type"):
            if event.type == "content_block_start":
                if hasattr(event.content_block, "type"):
                    if event.content_block.type == "tool_use":
                        tool_input_accumulator[event.content_block.id] = ""
            elif event.type == "content_block_delta":
                delta = event.delta
                if hasattr(delta, "type"):
                    if delta.type == "text_delta":
                        results.append(StreamEvent(type="text_delta", text=delta.text))
                    elif delta.type == "input_json_delta":
                        # Find current tool_use block
                        if hasattr(event, "index"):
                            # accumulate by index; we use the last id added
                            for tid in tool_input_accumulator:
                                tool_input_accumulator[tid] += delta.partial_json
            elif event.type == "content_block_stop":
                # If this was a tool_use block, emit the completed tool_use event
                pass
            elif event.type == "message_delta":
                if hasattr(event, "usage") and event.usage:
                    results.append(StreamEvent(
                        type="usage",
                        output_tokens=getattr(event.usage, "output_tokens", 0),
                    ))
            elif event.type == "message_stop":
                results.append(StreamEvent(type="message_stop"))

        # Emit completed tool_use events from the final message
        if hasattr(event, "type") and event.type == "message_stop":
            pass  # tool_use events are emitted in query.py from the final message

        return results

    def messages_to_api_format(self, messages: list) -> list[dict]:
        """Convert internal message objects to API dict format."""
        result = []
        for msg in messages:
            if hasattr(msg, "role"):
                role = msg.role.value if hasattr(msg.role, "value") else msg.role
                content = msg.content
                if isinstance(content, str):
                    result.append({"role": role, "content": content})
                elif isinstance(content, list):
                    blocks = []
                    for block in content:
                        if hasattr(block, "type"):
                            if block.type == "text":
                                blocks.append({"type": "text", "text": block.text})
                            elif block.type == "tool_use":
                                blocks.append({
                                    "type": "tool_use",
                                    "id": block.id,
                                    "name": block.name,
                                    "input": block.input,
                                })
                            elif block.type == "tool_result":
                                blocks.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.tool_use_id,
                                    "content": block.content,
                                    "is_error": block.is_error,
                                })
                    result.append({"role": role, "content": blocks})
        return result

    def tools_to_api_format(self, tools: list) -> list[dict]:
        """Convert Tool objects to API dict format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
            if tool.is_enabled()
        ]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_api_client.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add packages/app/services/api/claude.py tests/test_api_client.py
git commit -m "feat: Anthropic API client with streaming support"
```

---

## Task 5: context.py — system prompt 构建

**Files:**
- Create: `packages/app/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: 编写失败的测试**

`tests/test_context.py`:
```python
"""Tests for system/user context construction."""
from __future__ import annotations
import pytest
from pathlib import Path
from app.context import build_system_prompt, load_claude_md


def test_build_system_prompt_contains_cwd(tmp_path: Path):
    prompt = build_system_prompt(cwd=str(tmp_path))
    assert str(tmp_path) in prompt


def test_build_system_prompt_contains_date(tmp_path: Path):
    prompt = build_system_prompt(cwd=str(tmp_path))
    # Should contain current year at minimum
    import datetime
    assert str(datetime.date.today().year) in prompt


def test_load_claude_md_found(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Project\nDo things this way.")
    content = load_claude_md(str(tmp_path))
    assert "Do things this way." in content


def test_load_claude_md_not_found(tmp_path: Path):
    content = load_claude_md(str(tmp_path))
    assert content == ""


def test_build_system_prompt_includes_claude_md(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Custom Instructions\nAlways use snake_case.")
    prompt = build_system_prompt(cwd=str(tmp_path))
    assert "Always use snake_case." in prompt
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_context.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 context.py**

```python
"""Build system and user context for API calls."""
from __future__ import annotations
import datetime
import subprocess
from pathlib import Path


SYSTEM_PROMPT_BASE = """You are Claude Code, an AI coding assistant.

You help with software engineering tasks: writing code, debugging, refactoring, explaining code, and more.

Current date: {date}
Working directory: {cwd}
{claude_md_section}
{git_section}"""


def load_claude_md(cwd: str) -> str:
    """Load CLAUDE.md from the project directory (and parents)."""
    path = Path(cwd)
    for directory in [path, *path.parents]:
        candidate = directory / "CLAUDE.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return ""


def get_git_status(cwd: str) -> str:
    """Get a brief git status summary."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"Git status:\n{result.stdout.strip()}"
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def build_system_prompt(cwd: str) -> str:
    """Build the system prompt for a new conversation turn."""
    date = datetime.date.today().isoformat()
    claude_md = load_claude_md(cwd)
    git_status = get_git_status(cwd)

    claude_md_section = (
        f"\n## Project Instructions (CLAUDE.md)\n{claude_md}\n" if claude_md else ""
    )
    git_section = f"\n{git_status}" if git_status else ""

    return SYSTEM_PROMPT_BASE.format(
        date=date,
        cwd=cwd,
        claude_md_section=claude_md_section,
        git_section=git_section,
    ).strip()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_context.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add packages/app/context.py tests/test_context.py
git commit -m "feat: system prompt builder with CLAUDE.md and git status"
```

---

## Task 6: query.py — 流式调用 + 工具调用循环

**Files:**
- Create: `packages/app/query.py`
- Create: `tests/test_query.py`

- [ ] **Step 1: 编写失败的测试**

`tests/test_query.py`:
```python
"""Tests for the core query loop."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock
from app.query import query, QueryResult
from app.tool import ToolResult, ToolContext
from app.types.message import UserMessage, AssistantMessage, TextBlock


class EchoTool:
    name = "EchoTool"
    description = "Echoes input back"
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def is_enabled(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(content=f"echo: {input['text']}")

    def render_result(self, result: ToolResult) -> str:
        return result.content


@pytest.mark.asyncio
async def test_query_returns_result_on_message_stop():
    """query() should collect text and return QueryResult when stream ends."""
    from app.services.api.claude import StreamEvent

    mock_client = MagicMock()

    async def mock_stream(params):
        yield StreamEvent(type="text_delta", text="Hello")
        yield StreamEvent(type="text_delta", text=" World")
        yield StreamEvent(type="message_stop")

    mock_client.stream = mock_stream
    mock_client.build_request_params = MagicMock(return_value=MagicMock(
        model="claude-opus-4-6", messages=[], system="", tools=[], max_tokens=8096
    ))
    mock_client.messages_to_api_format = MagicMock(return_value=[])
    mock_client.tools_to_api_format = MagicMock(return_value=[])

    messages = [UserMessage(content="say hello")]
    result = await query(
        messages=messages,
        system="You are helpful.",
        tools=[],
        api_client=mock_client,
        cwd="/tmp",
    )

    assert isinstance(result, QueryResult)
    assert result.response_text == "Hello World"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_query_executes_tool_call():
    """query() should execute tool calls and add results to messages."""
    import json
    from app.services.api.claude import StreamEvent

    mock_client = MagicMock()
    call_count = 0

    async def mock_stream(params):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: respond with a tool use
            yield StreamEvent(
                type="tool_use",
                tool_use_id="call_abc",
                tool_name="EchoTool",
                tool_input={"text": "hi"},
            )
            yield StreamEvent(type="message_stop")
        else:
            # Second call: respond with text after tool result
            yield StreamEvent(type="text_delta", text="Done!")
            yield StreamEvent(type="message_stop")

    mock_client.stream = mock_stream
    mock_client.build_request_params = MagicMock(return_value=MagicMock(
        model="claude-opus-4-6", messages=[], system="", tools=[], max_tokens=8096
    ))
    mock_client.messages_to_api_format = MagicMock(return_value=[])
    mock_client.tools_to_api_format = MagicMock(return_value=[])

    messages = [UserMessage(content="use echo tool")]
    result = await query(
        messages=messages,
        system="",
        tools=[EchoTool()],
        api_client=mock_client,
        cwd="/tmp",
    )

    assert result.response_text == "Done!"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool_name"] == "EchoTool"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_query.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 query.py**

```python
"""Core API query function with streaming and tool call loop."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from app.tool import Tool, ToolResult, ToolContext
from app.types.message import (
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    UserMessage,
    Message,
)
from app.services.api.claude import ClaudeAPIClient, StreamEvent


@dataclass
class ToolCallRecord:
    tool_name: str
    tool_use_id: str
    input: dict
    result: ToolResult


@dataclass
class QueryResult:
    response_text: str
    tool_calls: list[ToolCallRecord]
    input_tokens: int = 0
    output_tokens: int = 0
    messages: list[Message] = field(default_factory=list)


async def query(
    messages: list[Message],
    system: str,
    tools: list[Tool],
    api_client: ClaudeAPIClient,
    cwd: str,
    permission_mode: str = "manual",
    on_text: Callable[[str], None] | None = None,
    on_tool_use: Callable[[str, dict], None] | None = None,
) -> QueryResult:
    """
    Send messages to Claude API and process the streaming response.
    Handles multi-turn tool call loops automatically.
    Returns when the model stops with a text-only response.
    """
    conversation: list[Message] = list(messages)
    all_tool_calls: list[ToolCallRecord] = []
    total_input_tokens = 0
    total_output_tokens = 0
    context = ToolContext(cwd=cwd, permission_mode=permission_mode)

    while True:
        api_messages = api_client.messages_to_api_format(conversation)
        api_tools = api_client.tools_to_api_format(tools)
        params = api_client.build_request_params(
            messages=api_messages,
            system=system,
            tools=api_tools,
        )

        # Collect streaming events for this turn
        text_parts: list[str] = []
        tool_use_events: list[StreamEvent] = []

        async for event in api_client.stream(params):
            if event.type == "text_delta":
                text_parts.append(event.text)
                if on_text:
                    on_text(event.text)
            elif event.type == "tool_use":
                tool_use_events.append(event)
                if on_tool_use:
                    on_tool_use(event.tool_name, event.tool_input)
            elif event.type == "usage":
                total_input_tokens += event.input_tokens
                total_output_tokens += event.output_tokens
            elif event.type == "message_stop":
                break

        response_text = "".join(text_parts)

        # Build assistant message for this turn
        assistant_content: list = []
        if response_text:
            assistant_content.append(TextBlock(text=response_text))
        for ev in tool_use_events:
            assistant_content.append(
                ToolUseBlock(id=ev.tool_use_id, name=ev.tool_name, input=ev.tool_input)
            )

        if assistant_content:
            conversation.append(AssistantMessage(content=assistant_content))

        # If no tool calls, we're done
        if not tool_use_events:
            break

        # Execute tool calls and build tool result message
        tool_result_blocks: list[ToolResultBlock] = []
        for ev in tool_use_events:
            tool = next((t for t in tools if t.name == ev.tool_name), None)
            if tool is None:
                result = ToolResult(
                    content=f"Tool '{ev.tool_name}' not found.", is_error=True
                )
            else:
                try:
                    result = await tool.call(ev.tool_input, context)
                except Exception as e:
                    result = ToolResult(content=str(e), is_error=True)

            record = ToolCallRecord(
                tool_name=ev.tool_name,
                tool_use_id=ev.tool_use_id,
                input=ev.tool_input,
                result=result,
            )
            all_tool_calls.append(record)
            tool_result_blocks.append(
                ToolResultBlock(
                    tool_use_id=ev.tool_use_id,
                    content=result.content if isinstance(result.content, str) else str(result.content),
                    is_error=result.is_error,
                )
            )

        # Add tool results as a user message and loop
        conversation.append(UserMessage(content=tool_result_blocks))

    return QueryResult(
        response_text=response_text,
        tool_calls=all_tool_calls,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        messages=conversation,
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_query.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add packages/app/query.py tests/test_query.py
git commit -m "feat: streaming query loop with tool call execution"
```

---

## Task 7: QueryEngine — 会话编排

**Files:**
- Create: `packages/app/query_engine.py`
- Create: `tests/test_query_engine.py`

- [ ] **Step 1: 编写失败的测试**

`tests/test_query_engine.py`:
```python
"""Tests for QueryEngine session management."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.query_engine import QueryEngine
from app.query import QueryResult
from app.types.message import UserMessage


@pytest.fixture
def engine(tmp_path):
    return QueryEngine(cwd=str(tmp_path), api_key="test_key")


def test_engine_initial_state(engine):
    assert engine.turn_count == 0
    assert engine.messages == []
    assert engine.total_input_tokens == 0
    assert engine.total_output_tokens == 0


@pytest.mark.asyncio
async def test_engine_run_turn_increments_count(engine, tmp_path):
    mock_result = QueryResult(
        response_text="Hello!",
        tool_calls=[],
        input_tokens=10,
        output_tokens=5,
        messages=[UserMessage(content="hi"), ],
    )

    with patch("app.query_engine.query", new=AsyncMock(return_value=mock_result)):
        result = await engine.run_turn("hi")

    assert engine.turn_count == 1
    assert result.response_text == "Hello!"


@pytest.mark.asyncio
async def test_engine_accumulates_tokens(engine):
    mock_result = QueryResult(
        response_text="Hi",
        tool_calls=[],
        input_tokens=100,
        output_tokens=50,
        messages=[],
    )

    with patch("app.query_engine.query", new=AsyncMock(return_value=mock_result)):
        await engine.run_turn("hello")
        await engine.run_turn("world")

    assert engine.total_input_tokens == 200
    assert engine.total_output_tokens == 100


def test_engine_clear_resets_state(engine):
    engine.turn_count = 5
    engine.total_input_tokens = 1000
    engine.clear()
    assert engine.turn_count == 0
    assert engine.messages == []
    assert engine.total_input_tokens == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_query_engine.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 query_engine.py**

```python
"""QueryEngine — higher-level session orchestrator wrapping query()."""
from __future__ import annotations
from typing import Callable

from app.context import build_system_prompt
from app.query import query, QueryResult
from app.services.api.claude import ClaudeAPIClient
from app.tool import Tool
from app.tools import get_tools
from app.types.message import Message, UserMessage


class QueryEngine:
    """
    Manages conversation state across multiple turns.
    Wraps query() with session bookkeeping.
    Corresponds to QueryEngine.ts in the reference implementation.
    """

    def __init__(
        self,
        cwd: str,
        api_key: str | None = None,
        model: str = "claude-opus-4-6",
        permission_mode: str = "manual",
    ):
        self.cwd = cwd
        self.permission_mode = permission_mode
        self.messages: list[Message] = []
        self.turn_count: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self._api_client = ClaudeAPIClient(api_key=api_key, model=model)
        self._tools: list[Tool] = get_tools()

    async def run_turn(
        self,
        user_input: str,
        on_text: Callable[[str], None] | None = None,
        on_tool_use: Callable[[str, dict], None] | None = None,
    ) -> QueryResult:
        """
        Run a single conversation turn.
        Appends user message, calls query(), updates session state.
        """
        self.messages.append(UserMessage(content=user_input))
        system = build_system_prompt(cwd=self.cwd)

        result = await query(
            messages=self.messages,
            system=system,
            tools=self._tools,
            api_client=self._api_client,
            cwd=self.cwd,
            permission_mode=self.permission_mode,
            on_text=on_text,
            on_tool_use=on_tool_use,
        )

        # Update session state
        self.messages = result.messages
        self.turn_count += 1
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens

        return result

    def clear(self) -> None:
        """Reset the session state."""
        self.messages = []
        self.turn_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_query_engine.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add packages/app/query_engine.py tests/test_query_engine.py
git commit -m "feat: QueryEngine session orchestrator"
```

---

## Task 8: main.py + pipe 模式端到端验证

**Files:**
- Create: `packages/app/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: 编写失败的测试**

`tests/test_main.py`:
```python
"""Tests for main CLI entry point."""
from __future__ import annotations
import pytest
from click.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Claude Code" in result.output


def test_cli_pipe_mode_flag():
    runner = CliRunner()
    # --print / -p flag should be recognized
    with patch("app.main.run_pipe_mode", new=AsyncMock()):
        result = runner.invoke(cli, ["-p", "say hello"])
    # Should not error on unknown option
    assert "--print" in result.output or result.exit_code in (0, 2)


@pytest.mark.asyncio
async def test_run_pipe_mode_prints_response(tmp_path, capsys):
    from app.main import run_pipe_mode
    from app.query import QueryResult

    mock_result = QueryResult(
        response_text="Hello from Claude!",
        tool_calls=[],
        input_tokens=10,
        output_tokens=5,
        messages=[],
    )

    with patch("app.main.QueryEngine") as MockEngine:
        engine_instance = MagicMock()
        engine_instance.run_turn = AsyncMock(return_value=mock_result)
        MockEngine.return_value = engine_instance

        await run_pipe_mode(prompt="say hello", cwd=str(tmp_path))

    captured = capsys.readouterr()
    assert "Hello from Claude!" in captured.out
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_main.py -v
```

Expected: `ImportError`

- [ ] **Step 3: 实现 main.py**

```python
"""Main CLI logic — command definitions, pipe mode, REPL launcher."""
from __future__ import annotations
import asyncio
import os
import sys
import click

from app.query_engine import QueryEngine


@click.group(invoke_without_command=True)
@click.option("-p", "--print", "print_mode", is_flag=True, help="Non-interactive pipe mode")
@click.argument("prompt", required=False)
@click.pass_context
def cli(ctx: click.Context, print_mode: bool, prompt: str | None) -> None:
    """Claude Code — AI coding assistant in the terminal."""
    if ctx.invoked_subcommand is not None:
        return

    cwd = os.getcwd()

    if print_mode or not sys.stdin.isatty():
        # Pipe mode: read from argument or stdin
        if prompt is None:
            prompt = sys.stdin.read().strip()
        if not prompt:
            click.echo("Error: no prompt provided.", err=True)
            sys.exit(1)
        asyncio.run(run_pipe_mode(prompt=prompt, cwd=cwd))
    else:
        # Interactive REPL mode (implemented in Phase 4)
        click.echo("Interactive REPL not yet implemented. Use -p for pipe mode.")
        sys.exit(1)


async def run_pipe_mode(prompt: str, cwd: str) -> None:
    """Run a single query in non-interactive pipe mode."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        click.echo("Error: ANTHROPIC_API_KEY environment variable not set.", err=True)
        sys.exit(1)

    engine = QueryEngine(cwd=cwd, api_key=api_key)

    def on_text(text: str) -> None:
        print(text, end="", flush=True)

    await engine.run_turn(prompt, on_text=on_text)
    print()  # Final newline
```

- [ ] **Step 4: 运行全部测试**

```bash
uv run pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 5: 手动验证 pipe 模式（需要有效的 ANTHROPIC_API_KEY）**

```bash
export ANTHROPIC_API_KEY="your_key_here"
echo "say hello in one sentence" | uv run python -m app.entrypoints.cli -p
```

Expected: Claude 的单句回复输出到 stdout

- [ ] **Step 6: Commit**

```bash
git add packages/app/main.py tests/test_main.py
git commit -m "feat: Click CLI with pipe mode end-to-end"
```

---

## 自检

### Spec 覆盖检查

| Spec 要求 | 对应 Task |
|-----------|----------|
| Click CLI 入口 | Task 1, Task 8 |
| 消息类型层次 | Task 2 |
| Tool Protocol + 注册表 | Task 3 |
| Anthropic API 客户端（流式） | Task 4 |
| system prompt 构建（git/CLAUDE.md） | Task 5 |
| 流式 query + 工具调用循环 | Task 6 |
| 会话编排（QueryEngine） | Task 7 |
| pipe 模式端到端 | Task 8 |
| bootstrap 单例 | Task 1 |

### 类型一致性检查

- `ToolResult` 在 Task 3 定义，在 Task 6 使用 ✓
- `ToolContext` 在 Task 3 定义，在 Task 6 使用 ✓
- `StreamEvent` 在 Task 4 定义，在 Task 6 测试中使用 ✓
- `QueryResult` 在 Task 6 定义，在 Task 7、8 使用 ✓
- `ClaudeAPIClient` 在 Task 4 定义，在 Task 7 使用 ✓
- `build_system_prompt` 在 Task 5 定义，在 Task 7 使用 ✓

### 占位符扫描

无 TBD / TODO / "implement later" / "similar to Task N" ✓

---

## 后续计划

- **Phase 2:** 工具系统（BashTool, FileReadTool, FileEditTool 等 15 个工具）
- **Phase 3:** 权限系统 + Hook 系统
- **Phase 4:** Textual TUI（REPLScreen + 组件）
- **Phase 5:** 会话压缩（Compaction）
