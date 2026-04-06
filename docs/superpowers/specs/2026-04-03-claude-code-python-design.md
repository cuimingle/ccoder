# Claude Code Python — Design Spec

**Date:** 2026-04-03  
**Status:** Approved  
**Reference:** `/Users/mingcui/Documents/文稿/claude-code-run` (TypeScript/Bun 逆向版)

---

## 1. 目标

用 Python 完整复现 Claude Code CLI 工具的核心功能，包括：

- 终端 REPL 交互界面（Textual TUI）
- 与 Claude API 的流式通信（Anthropic Direct，后续可扩展）
- 工具调用系统（15个工具：核心+高级）
- 完整权限系统（plan/auto/manual 模式）
- Hook 系统（pre/post tool use，settings.json 配置）
- 会话管理（压缩、恢复、状态持久化）

MCP 支持暂不实现，作为后期扩展预留。

---

## 2. 技术选型

| 功能 | 选型 | 对应原版 |
|------|------|---------|
| CLI 解析 | `click` | Commander.js |
| TUI 框架 | `textual` | React/Ink |
| Anthropic API | `anthropic` 官方 SDK | `@anthropic-ai/sdk` |
| 异步运行时 | `asyncio` | Bun async |
| 配置文件解析 | `json5` | `jsonc-parser` |
| 包管理 | `uv` | bun |
| 测试 | `pytest` + `pytest-asyncio` | bun test |

Python 版本要求：≥ 3.11（使用 `tomllib`、`match` 语句、`ExceptionGroup` 等特性）

---

## 3. 整体架构

### 数据流

```
cli.py → main.py → QueryEngine → query() → Claude API (streaming)
                                     ↓
                               工具调用循环
                                     ↓
                      tools/BashTool, FileEditTool, ...
                                     ↓
                         permissions/ (授权检查)
                                     ↓
                         services/hooks/ (pre/post)
```

### UI 层

```
screens/REPLScreen (Textual App)
  ├── components/Messages          # 消息列表（流式渲染）
  ├── components/PromptInput       # 用户输入框
  └── components/PermissionPrompt  # 工具授权确认 UI
       └── state/AppState          # 中心状态（dataclass）
```

---

## 4. 模块职责

| 模块 | 对应原版 | 职责 |
|------|---------|------|
| `entrypoints/cli.py` | `entrypoints/cli.tsx` | Click 入口，注入 polyfill 全局状态 |
| `main.py` | `main.tsx` | CLI 命令定义，初始化服务，启动 REPL 或 pipe 模式 |
| `query.py` | `query.ts` | 流式 API 调用、工具调用循环、token 追踪、自动压缩触发 |
| `query_engine.py` | `QueryEngine.ts` | 会话状态、compaction 管理、turn 级 bookkeeping |
| `context.py` | `context.ts` | 构建 system/user context（git status、CLAUDE.md、memory files） |
| `tool.py` | `Tool.ts` | `Tool` Protocol 定义，`find_tool_by_name`，`ToolResult` 类型 |
| `tools.py` | `tools.ts` | 工具注册表，按条件组装工具列表 |
| `services/api/claude.py` | `services/api/claude.ts` | Anthropic SDK 封装，streaming，构建 request params |
| `services/compact/` | `services/compact/` | auto / micro / API 三种压缩策略 |
| `services/hooks/tool_hooks.py` | `services/tools/toolHooks.ts` | pre/post tool use hook 执行（subprocess） |
| `permissions/` | `permissions/` | plan/auto/manual 模式、路径验证、规则匹配 |
| `state/app_state.py` | `state/AppState.tsx` | 中心应用状态（frozen dataclass + asyncio Event） |
| `bootstrap/state.py` | `bootstrap/state.py` | 模块级单例（session ID、CWD、token counts） |
| `screens/repl.py` | `screens/REPL.tsx` | Textual App 主屏幕，输入处理、消息显示、快捷键 |
| `components/` | `components/` | Textual Widget 组件 |
| `types/message.py` | `types/message.ts` | 消息类型层次（UserMessage、AssistantMessage 等） |
| `types/permissions.py` | `types/permissions.ts` | 权限模式和结果类型 |

---

## 5. 工具系统

### Tool Protocol

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict  # JSON Schema

    async def call(self, input: dict, context: "ToolContext") -> "ToolResult": ...
    def is_enabled(self) -> bool: ...
    def render_result(self, result: "ToolResult") -> str: ...  # 可选，用于 TUI 渲染
```

### 实现的 15 个工具

**始终启用（10个）：**
- `BashTool` — Shell 执行，沙箱，权限检查
- `FileReadTool` — 文件/PDF/图片读取
- `FileEditTool` — 字符串替换式编辑 + diff 追踪
- `FileWriteTool` — 文件创建/覆写 + diff 生成
- `GrepTool` — 基于 ripgrep/grep 的内容搜索
- `GlobTool` — 文件名模式匹配
- `WebFetchTool` — URL 抓取 → Markdown → AI 摘要
- `WebSearchTool` — 网页搜索 + 域名过滤
- `AskUserQuestionTool` — 多问题交互提示
- `AgentTool` — 子代理派生

**条件启用（5个）：**
- `NotebookEditTool` — Jupyter Notebook 单元格编辑
- `TaskCreateTool` — Task 列表创建
- `TaskUpdateTool` — Task 状态更新
- `TaskListTool` — Task 列表查看
- `TaskGetTool` — Task 详情获取

---

## 6. 权限系统

### 三种模式

| 模式 | 行为 |
|------|------|
| `manual`（默认） | 每次工具调用前在 TUI 弹出确认框 |
| `auto` | 按 `settings.json` 中的规则自动允许/拒绝，无匹配则弹框 |
| `plan` | 只允许只读工具（FileRead/Grep/Glob），写操作一律拒绝 |

### 规则匹配（auto 模式）

`~/.claude/settings.json`:
```json
{
  "permissions": {
    "allow": ["Bash(git *)", "FileEdit(/home/user/project/*)"],
    "deny": ["Bash(rm -rf *)"]
  }
}
```

规则语法：`ToolName(pattern)`，pattern 支持 glob 匹配。

### 路径验证

- 禁止访问 `~/.ssh/`, `~/.aws/`, `/etc/` 等敏感路径
- 禁止路径穿越（`../` 超出项目根目录）
- 可配置白名单（`allowedPaths`）

---

## 7. Hook 系统

`~/.claude/settings.json` 配置：
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "echo 'pre bash hook'"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "logger 'tool used'"}]
      }
    ]
  }
}
```

Hook 执行方式：
- 以子进程方式运行 shell 命令（`asyncio.create_subprocess_shell`）
- PreToolUse hook 的 exit code 非 0 时中止工具执行
- PostToolUse hook 仅做通知，不影响结果
- 超时 30 秒

---

## 8. 会话压缩（Compaction）

三种策略（对应原版）：

| 策略 | 触发条件 | 实现 |
|------|---------|------|
| `auto-compact` | token 数超过上下文窗口 90% | 调用 API 生成摘要替换历史 |
| `micro-compact` | 单轮消息过长 | 本地截断 + 摘要 |
| `api-compact` | 用户手动 `/compact` | 完整调用 API 压缩 |

---

## 9. 项目结构

```
claude-code-python/
├── src/
│   ├── entrypoints/
│   │   └── cli.py               # Click 入口
│   ├── main.py                  # 主 CLI 逻辑
│   ├── query.py                 # 流式 API + 工具调用循环
│   ├── query_engine.py          # 会话编排
│   ├── context.py               # system prompt 构建
│   ├── tool.py                  # Tool Protocol + ToolResult
│   ├── tools.py                 # 工具注册表
│   ├── tools/
│   │   ├── BashTool/
│   │   │   ├── __init__.py
│   │   │   └── bash_tool.py
│   │   ├── FileReadTool/
│   │   ├── FileEditTool/
│   │   ├── FileWriteTool/
│   │   ├── GrepTool/
│   │   ├── GlobTool/
│   │   ├── WebFetchTool/
│   │   ├── WebSearchTool/
│   │   ├── AskUserQuestionTool/
│   │   ├── AgentTool/
│   │   ├── NotebookEditTool/
│   │   └── TaskTool/
│   ├── services/
│   │   ├── api/
│   │   │   └── claude.py
│   │   ├── compact/
│   │   │   ├── auto_compact.py
│   │   │   ├── micro_compact.py
│   │   │   └── api_compact.py
│   │   └── hooks/
│   │       └── tool_hooks.py
│   ├── screens/
│   │   └── repl.py
│   ├── components/
│   │   ├── messages.py
│   │   ├── prompt_input.py
│   │   └── permission_prompt.py
│   ├── state/
│   │   └── app_state.py
│   ├── permissions/
│   │   ├── __init__.py
│   │   ├── checker.py
│   │   └── rules.py
│   ├── bootstrap/
│   │   └── state.py
│   └── types/
│       ├── message.py
│       └── permissions.py
├── tests/
├── pyproject.toml
├── CLAUDE.md
└── README.md
```

---

## 10. 非目标（本期不实现）

- MCP（Model Context Protocol）支持
- AWS Bedrock / Google Vertex / Azure provider
- 会话历史持久化（`/resume`）
- 插件系统
- OAuth 认证（只用 API Key）
- LSP 工具
- 语音模式
