# Python 实现 vs TypeScript 原版功能对比分析

> 对比基准：Python (`claude-code-python`) vs TypeScript (`claude-code-run`)
> 生成日期：2026-04-06

---

## 总览

| 维度 | Python 实现 | TypeScript 原版 | 完成度 |
|------|------------|----------------|--------|
| 工具数量 | 20 | 56 | ~36% |
| 斜杠命令 | 22 | 95+ | ~23% |
| 权限模式 | 3 | 7+ | ~43% |
| Hook 事件类型 | 2 | 15 | ~13% |
| Feature Flags | 2 | 31 | ~6% |
| MCP 支持 | 无 | 完整 | 0% |
| API Provider | 1 (Anthropic) | 4 (Anthropic/Bedrock/Vertex/Azure) | 25% |
| 源文件规模 | ~50 文件 | ~2,780 文件 | - |

---

## 1. 工具系统差异

### Python 已实现的工具 (20)

| 工具名 | 状态 | 备注 |
|--------|------|------|
| Read / Edit / Write | ✅ 已实现 | 基本对齐 |
| Glob / Grep | ✅ 已实现 | 基本对齐 |
| Bash | ✅ 已实现 | 基本对齐 |
| WebSearch / WebFetch | ✅ 已实现 | 基本对齐 |
| NotebookEdit | ✅ 已实现 | 基本对齐 |
| Agent | ✅ 已实现 | 支持子 agent、worktree 隔离、后台执行 |
| Skill | ✅ 已实现 | 基本对齐 |
| TaskCreate/Update/List/Get/Stop/Output | ✅ 已实现 | 基本对齐 |
| EnterWorktree / ExitWorktree | ✅ 已实现 | 基本对齐 |
| EnterPlanMode / ExitPlanMode | ✅ 已实现 | 基本对齐 |
| AskUserQuestion | ✅ 已实现 | 基本对齐 |
| SendMessage | ✅ 已实现 | 基本对齐 |
| ToolSearch | ✅ 已实现 | 基本对齐 |
| CronCreate/List/Delete | ✅ 已实现 | 基本对齐 |

### TypeScript 独有的工具 (Python 未实现)

| 工具名 | 功能 | 优先级建议 |
|--------|------|-----------|
| **TodoWriteTool** | Todo 列表 v1（与 TaskCreate 并存） | 低 - Task 系统已覆盖 |
| **BriefTool** | 短消息 + 附件发送 | 低 - Kairos 特性 |
| **ListMcpResourcesTool** | 列出 MCP 资源 | 高 - MCP 核心功能 |
| **ReadMcpResourceTool** | 读取 MCP 资源 | 高 - MCP 核心功能 |
| **PowerShellTool** | Windows PowerShell 执行 | 中 - 跨平台支持 |
| **LSPTool** | Language Server Protocol 集成 | 中 - IDE 集成 |
| **TeamCreateTool / TeamDeleteTool** | Agent Swarm 团队管理 | 低 - 实验特性 |
| **SleepTool** | Proactive/Kairos 定时 | 低 - 实验特性 |
| **RemoteTriggerTool** | 远程触发 | 低 - 实验特性 |
| **MonitorTool** | 监控工具 | 低 - 实验特性 |
| **WebBrowserTool** | 浏览器操作 | 低 - 实验特性 |
| **SnipTool** | 历史片段管理 | 低 - 实验特性 |
| **WorkflowTool** | 工作流脚本 | 低 - 实验特性 |
| 其他 Feature Flag 工具 (6+) | 各种实验性工具 | 低 |

---

## 2. 斜杠命令差异

### Python 已实现 (22 个)

`/clear`, `/compact`, `/cost`, `/help`, `/session`, `/resume`, `/rewind`, `/branch`, `/config`, `/permissions`, `/hooks`, `/model`, `/cwd`, `/add-dir`, `/stats`, `/status`, `/doctor`, `/context`, `/usage`, `/diff`, `/export`, `/files`, `/exit`

### TypeScript 独有的重要命令 (Python 未实现)

| 命令 | 功能 | 优先级 |
|------|------|--------|
| `/vim` | Vim 模式切换 | 中 |
| `/fast` | 快速模式切换（思考 token 控制） | 高 |
| `/effort` | 设置 effort level | 高 |
| `/theme` | 终端主题选择 | 低 |
| `/mcp` | MCP 服务器管理 | 高 |
| `/memory` | CLAUDE.md 记忆管理 | 中 |
| `/login` / `/logout` | OAuth 认证 | 高 |
| `/init` | 项目初始化（生成 CLAUDE.md） | 中 |
| `/review` | 本地代码审查 | 中 |
| `/ultrareview` | 云端代码审查 | 低 |
| `/security-review` | 安全审查 | 中 |
| `/skills` | Skill 管理 | 中 |
| `/plugin` | 插件管理 | 中 |
| `/keybindings` | 快捷键自定义 | 低 |
| `/sandbox-toggle` | 沙箱模式切换 | 中 |
| `/upgrade` | CLI 自动更新 | 低 |
| `/ide` | IDE 连接管理 | 中 |
| `/desktop` | Claude Desktop 集成 | 低 |
| `/chrome` | Chrome 集成 | 低 |
| `/loop` | 循环执行（bundled skill） | 中 |
| `/color` | Agent 颜色选择 | 低 |
| `/agents` | Agent 列表/管理 | 中 |
| `/tasks` | 任务管理界面 | 中 |
| `/output-style` | 输出风格配置 | 低 |
| `/pr-comments` | PR 评论管理 | 中 |
| `/plan` | Plan 模式进入 | 中 |
| `/copy` | 复制上一条消息 | 低 |
| `/insights` | 分析报告 | 低 |
| `/mobile` | 移动端二维码 | 低 |
| `/feedback` | 反馈发送 | 低 |
| 其他 40+ 命令 | 各种功能 | - |

---

## 3. 权限系统差异

| 特性 | Python | TypeScript |
|------|--------|-----------|
| 权限模式数量 | 3 (MANUAL/AUTO/PLAN) | 7+ (default/auto/plan/bypass/dontAsk/acceptEdits/bubble) |
| 规则来源 | 2 (user/project settings) | 6 (user/project/local/flag/policy/cliArg) |
| YOLO 分类器 | ❌ 无 | ✅ 2-stage AI 分类 (fast + thinking) |
| 决策原因追踪 | ❌ 无 | ✅ 完整追踪（rule/mode/hook/classifier/workingDir/safetyCheck） |
| 敏感路径保护 | ✅ 基础（~/.ssh, ~/.aws 等） | ✅ 更全面 |
| 路径遍历检查 | ✅ 已实现 | ✅ 已实现 |
| 策略设置(Policy) | ❌ 无 | ✅ 组织级策略强制 |
| 会话级覆盖 | ✅ 已实现 | ✅ 已实现 |

---

## 4. Hook 系统差异

| 特性 | Python | TypeScript |
|------|--------|-----------|
| **支持的 Hook 事件** | 2 种 | 15 种 |
| PreToolUse | ✅ | ✅ |
| PostToolUse | ✅ | ✅ |
| PostToolUseFailure | ❌ | ✅ |
| UserPromptSubmit | ❌ | ✅ |
| SessionStart | ❌ | ✅ |
| Setup | ❌ | ✅ |
| SubagentStart | ❌ | ✅ |
| PermissionDenied | ❌ | ✅ |
| FileChanged | ❌ | ✅ |
| CwdChanged | ❌ | ✅ |
| WorktreeCreate | ❌ | ✅ |
| Notification | ❌ | ✅ |
| PermissionRequest | ❌ | ✅ |
| Elicitation / ElicitationResult | ❌ | ✅ |
| Hook 响应类型 | 基础(block/allow) | 丰富(continue/suppressOutput/stopReason/decision/systemMessage) |

---

## 5. API & Provider 差异

| 特性 | Python | TypeScript |
|------|--------|-----------|
| Anthropic Direct API | ✅ | ✅ |
| AWS Bedrock | ❌ | ✅ |
| Google Vertex AI | ❌ | ✅ |
| Azure Foundry | ❌ | ✅ |
| OAuth 认证 | ❌ | ✅ |
| API Key 认证 | ✅ | ✅ |
| Token Refresh | ❌ | ✅ |
| 策略限制强制 | ❌ | ✅ |

---

## 6. MCP (Model Context Protocol) 支持

| 特性 | Python | TypeScript |
|------|--------|-----------|
| MCP 完整支持 | ❌ 无 | ✅ 完整 |
| stdio 传输 | - | ✅ |
| SSE 传输 | - | ✅ |
| in-process 传输 | - | ✅ |
| MCP 工具桥接 | - | ✅ |
| 资源读取/列表 | - | ✅ |
| Elicitation | - | ✅ |
| CLI 管理命令 | - | ✅ (`claude mcp add/remove/list/get/invoke/resources`) |

**结论：MCP 是 TypeScript 版的重要特性，Python 版完全未实现。**

---

## 7. TUI / 终端界面差异

| 特性 | Python (Textual) | TypeScript (React + Ink) |
|------|------------------|--------------------------|
| UI 框架 | Python Textual | React 19 + 自定义 Ink reconciler |
| 布局引擎 | Textual CSS | Yoga Flexbox |
| Vim 模式 | ❌ | ✅ 完整实现（motions/operators/text objects） |
| 主题选择 | ❌ | ✅ 多主题（light/dark variants） |
| 图片粘贴 | ❌ | ✅ 剪贴板集成 |
| 语法高亮代码块 | 基础 | ✅ highlight.js 完整支持 |
| Diff 可视化 | 基础文本 | ✅ 结构化 Side-by-side diff |
| 搜索/高亮 | ❌ | ✅ |
| 超链接支持 | ❌ | ✅ 终端超链接检测 |
| 鼠标支持 | 基础 (Textual 内建) | ✅ 完整鼠标事件处理 |
| 选中复制 | 基础 | ✅ Copy-on-Select |
| 状态栏 | ✅ 基础 | ✅ 丰富（mode/token/effort/model） |
| 输入模式 | 2 (PROMPT/BASH) | 4 (prompt/bash/orphaned-permission/task-notification) |
| 多行输入 | 基础 | ✅ 完整多行编辑 |
| 快捷键自定义 | ❌ | ✅ `~/.claude/keybindings.json` |
| 组件数量 | ~5 | 145+ |

---

## 8. 会话管理差异

| 特性 | Python | TypeScript |
|------|--------|-----------|
| 会话保存/恢复 | ✅ 基础 | ✅ 完整（专用 ResumeConversation 屏幕） |
| 会话导出 | ✅ | ✅ |
| 会话分支(fork) | ✅ `/branch` | ✅ `/branch` + `/fork`(Feature Flag) |
| 自动压缩 | ✅ 90% 阈值触发 | ✅ 多级压缩 |
| 微压缩 | ✅ >10,000字符截断 | ✅ |
| 反应式压缩 | ✅ prompt-too-long 处理 | ✅ + REACTIVE_COMPACT feature |
| Snip 压缩 | ❌ | ✅ HISTORY_SNIP feature |
| 工具结果预算 | ✅ 基础 | ✅ 更精细 |

---

## 9. 状态管理差异

| 特性 | Python | TypeScript |
|------|--------|-----------|
| 状态库 | 自定义 dataclass | Zustand (React hooks) |
| 文件编辑历史追踪 | 基础 (read_file_state LRU) | ✅ 完整 FileHistoryState |
| 归因追踪 | ❌ | ✅ AttributionState |
| 拒绝追踪 | ❌ | ✅ DenialTrackingState |
| 插件状态 | ❌ | ✅ |
| 邮箱系统 | ❌ | ✅ MailboxProvider |
| 语音状态 | ❌ | ✅ VoiceProvider |

---

## 10. 其他重要差异

### Python 未实现的大模块

| 模块 | 说明 |
|------|------|
| **MCP 支持** | 完整的 Model Context Protocol 集成，包括服务器管理、资源读写、工具桥接 |
| **插件系统** | 插件发现、验证、加载、管理，自定义 CLI 命令扩展 |
| **Skills 系统** | 本地 skill 文件管理、远程 skill 发现/安装 |
| **多 Provider** | Bedrock/Vertex/Azure 等云服务商支持 |
| **OAuth 认证** | claude.ai OAuth 2.0 登录流程 |
| **IDE 集成** | Bridge 模式、远程控制、URL 协议处理 |
| **Vim 模式** | 完整的 Vim 键绑定（motions/operators/text objects） |
| **遥测/分析** | OpenTelemetry、GrowthBook feature flags、Sentry |
| **主题系统** | 多主题支持（light/dark variants） |
| **Computer Use** | Computer Use MCP、AppleScript/JXA 自动化 |
| **语音输入** | 麦克风输入、按键通话 |
| **桌面集成** | Claude Desktop 应用集成 |
| **Chrome 集成** | 浏览器扩展集成 |
| **移动端** | QR 码移动端连接 |
| **团队记忆** | 跨 Agent 记忆同步 |
| **沙箱模式** | 工具执行沙箱隔离 |
| **自动更新** | CLI 版本升级 |

### Python 独有或改进之处

| 特性 | 说明 |
|------|------|
| **Textual TUI** | 使用 Python 原生 TUI 框架，安装更轻量 |
| **uv 包管理** | 使用 uv 替代 npm/bun，启动更快 |
| **AsyncIO** | 全栈异步，Python 原生协程 |
| **Protocol-based Tools** | 使用 Python Protocol 而非继承，更灵活 |

---

## 11. Query Engine / 核心循环差异

| 特性 | Python | TypeScript |
|------|--------|-----------|
| 流式响应 | ✅ | ✅ |
| 流式工具执行 | ✅ StreamingToolExecutor | ✅ |
| 并发工具执行 | ✅ concurrent_safe 标记 | ✅ |
| 自动续写(max_output_tokens) | ✅ 最多 3 次 | ✅ |
| 模型回退(529 错误) | ✅ | ✅ |
| prompt-too-long 处理 | ✅ 反应式压缩 | ✅ |
| 恢复路径数 | 7 | 更多 |
| 终止状态数 | 10 | 更多 |
| 工具使用摘要生成 | ❌ | ✅ |
| Extended Thinking | ✅ ThinkingBlock | ✅ 更精细的 budget 控制 |
| Effort Level 控制 | ❌ | ✅ |

---

## 12. Feature Flags 差异

| | Python | TypeScript |
|---|--------|-----------|
| 数量 | 2 | 31 |
| Python 有的 | `STREAMING_TOOL_EXECUTION`, `EMIT_TOOL_USE_SUMMARIES` | - |
| TypeScript 独有重要的 | - | `VOICE_MODE`, `BRIDGE_MODE`, `KAIROS`, `PROACTIVE`, `HISTORY_SNIP`, `WORKFLOW_SCRIPTS`, `MCP_SKILLS`, `COORDINATOR_MODE` 等 |

---

## 总结

Python 实现已经覆盖了 Claude Code 的**核心功能骨架**：基本的工具系统、权限管理、会话管理、流式 API 调用、自动压缩和 TUI 交互。但与 TypeScript 原版相比，在以下方面有显著差距：

1. **MCP 支持**（完全缺失）—— 这是最重要的缺失，MCP 是 Claude Code 生态的核心扩展机制
2. **多 Provider 支持**（仅 Anthropic Direct）—— 企业用户需要 Bedrock/Vertex/Azure
3. **命令丰富度**（22 vs 95+）—— 许多便利命令未实现
4. **Hook 事件覆盖**（2 vs 15）—— 自动化能力受限
5. **TUI 成熟度**（基础 vs 145+ 组件）—— UI 功能和体验差距大
6. **插件/Skill 生态**—— 完全未实现
7. **IDE/桌面集成**—— 完全未实现
