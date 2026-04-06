<p align="center">
  <a href="README.md">English</a> |
  <a href="README_zh.md">简体中文</a>
</p>

# CCoder

Claude Code CLI 的 Python 实现 —— 一个集成了流式 API、Textual TUI 界面、可扩展工具系统和权限/钩子机制的 AI 编程助手。

## 环境要求

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) 包管理器
- Anthropic API Key

## 安装

```bash
# 克隆仓库
git clone <repo-url>
cd ccoder

# 安装依赖
uv sync

# 设置 API Key 和 Base URL
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_BASE_URL="https://api.anthropic.com"  # 可选，用于自定义端点
```

## 使用方法

```bash
# 启动交互式 TUI
uv run ccoder

# 管道模式（非交互）
echo "解释这段代码" | uv run ccoder --print

# 单次查询
uv run ccoder --print "这个项目是做什么的？"
```

## 开发

```bash
# 运行所有测试
uv run pytest

# 运行单个测试文件
uv run pytest tests/tools/test_bash_tool.py -x -v

# 运行特定测试
uv run pytest tests/tools/test_bash_tool.py::test_function_name -x -v
```

## 功能特性

### 核心功能

- [x] **流式 AI 对话** — 来自 Claude API 的实时流式响应
- [x] **交互式 TUI** — 基于 [Textual](https://github.com/Textualize/textual) 构建的终端界面
- [x] **管道模式** — 支持脚本化的非交互模式（`--print` 或 stdin）
- [x] **自动压缩** — 智能上下文管理，自动进行对话压缩
- [x] **斜杠命令** — 内置命令（`/clear`、`/compact`、`/cost`、`/help`）

### 工具系统

- [x] 文件读取 / 写入 / 编辑
- [x] Bash 命令执行（支持超时和后台运行）
- [x] Glob 和 Grep 搜索（集成 ripgrep）
- [x] 网页抓取与搜索
- [x] Jupyter Notebook 编辑
- [x] Agent 编排与子代理
- [x] 任务管理
- [x] Git Worktree 管理
- [x] Plan 模式（进入 / 退出）
- [x] Cron 定时任务调度
- [x] 工具搜索（延迟加载工具）

### 权限与安全

- [x] 三种权限模式 — Plan（只读）/ Auto（规则驱动）/ Manual（交互确认）
- [x] 可配置的允许/拒绝规则，支持 fnmatch 通配符
- [x] 敏感路径保护（~/.ssh、~/.aws 等）
- [x] 工具使用前后的自定义 Shell 命令钩子

### 配置

- [x] 用户级设置（`~/.claude/settings.json`）
- [x] 项目级设置（`.claude/settings.json`）
- [x] CLAUDE.md 指令层级（全局 / 项目 / 本地）

### 计划中

- [ ] MCP（Model Context Protocol）服务器支持
- [ ] 对话历史持久化与恢复
- [ ] 多模型支持（运行时切换模型）
- [ ] 插件 / 扩展系统
- [ ] IDE 集成（VS Code / JetBrains 插件）
- [ ] 自定义 TUI 主题
- [ ] OAuth 认证
- [ ] 国际化 / 多语言支持

## 架构

```
cli.py → main.py (Click CLI)
  ├── 交互模式: ClaudeCodeApp (Textual TUI)
  └── 管道模式: 单次非交互查询

QueryEngine（会话编排器）
  → query()（单轮对话：流式响应 + 工具循环）
    1. 通过流式调用 Claude API
    2. 收集文本/工具调用事件
    3. 执行工具调用 → 追加结果 → 循环
    4. 达到 max_output_tokens 时自动续写
    5. 遇到 prompt_too_long 时触发压缩
```

### 核心组件

| 组件 | 说明 |
|---|---|
| `app/query_engine.py` | 会话编排器，管理对话流程 |
| `app/query/loop.py` | 核心查询循环，处理流式响应和工具执行 |
| `app/services/api/` | Claude API 客户端，含重试和流式处理 |
| `app/tools/` | 所有内置工具的实现 |
| `app/tool.py` | Tool Protocol 定义 |
| `app/permissions.py` | 权限检查（Plan/Auto/Manual 模式） |
| `app/hooks.py` | 工具使用前后的钩子执行 |
| `app/compaction.py` | 上下文窗口管理与压缩 |
| `app/screens/repl.py` | Textual TUI 界面 |
| `app/settings.py` | 设置加载器（~/.claude/settings.json） |

## 配置

设置文件加载顺序：
- `~/.claude/settings.json`（用户级）
- `.claude/settings.json`（项目级）

权限规则使用 `ToolName(pattern)` 格式，支持 fnmatch 通配符，在 `permissions.allow` / `permissions.deny` 下配置。

## 许可证

MIT
