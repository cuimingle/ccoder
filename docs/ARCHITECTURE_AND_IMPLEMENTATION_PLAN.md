# Claude Code 架构分析与复刻实施计划

> 本文档基于对当前代码库（反编译版 Claude Code CLI）的深度分析，输出完整架构设计细节和 1:1 功能复刻的分期实施计划。

---

## 目录

- [第一部分：项目概览](#第一部分项目概览)
- [第二部分：架构全景图](#第二部分架构全景图)
- [第三部分：核心模块详细分析](#第三部分核心模块详细分析)
  - [3.1 入口与启动流程](#31-入口与启动流程)
  - [3.2 核心对话循环](#32-核心对话循环)
  - [3.3 API 层与流式处理](#33-api-层与流式处理)
  - [3.4 工具系统](#34-工具系统)
  - [3.5 权限系统](#35-权限系统)
  - [3.6 UI 层与终端渲染](#36-ui-层与终端渲染)
  - [3.7 状态管理](#37-状态管理)
  - [3.8 上下文与系统提示词](#38-上下文与系统提示词)
  - [3.9 Hooks 系统](#39-hooks-系统)
  - [3.10 会话持久化](#310-会话持久化)
  - [3.11 MCP 协议集成](#311-mcp-协议集成)
  - [3.12 子代理系统](#312-子代理系统)
- [第四部分：技术栈与依赖](#第四部分技术栈与依赖)
- [第五部分：复刻实施计划](#第五部分复刻实施计划)
  - [Phase 1: 基础骨架（MVP）](#phase-1-基础骨架mvp)
  - [Phase 2: 核心工具链](#phase-2-核心工具链)
  - [Phase 3: 交互式 REPL](#phase-3-交互式-repl)
  - [Phase 4: 对话管理与持久化](#phase-4-对话管理与持久化)
  - [Phase 5: 权限与安全](#phase-5-权限与安全)
  - [Phase 6: 高级功能](#phase-6-高级功能)
  - [Phase 7: 扩展生态](#phase-7-扩展生态)
  - [Phase 8: 生产化](#phase-8-生产化)

---

## 第一部分：项目概览

### 项目规模

| 指标 | 数值 |
|------|------|
| **源码文件 (.ts/.tsx)** | ~2,780 个 |
| **源码体积** | ~25 MB |
| **CLI 命令** | 108 个 |
| **内置工具** | 56 个 |
| **React 组件** | 145+ 个 |
| **React Hooks** | 86 个 |
| **内部包** | 8 个 |
| **依赖包** | 150+ 个 |

### 技术栈

| 技术 | 用途 |
|------|------|
| **Bun** | 运行时 + 构建工具 |
| **TypeScript / TSX** | 编程语言 |
| **React 19 + 自定义 Ink** | 终端 UI 渲染 |
| **Commander.js** | CLI 参数解析 |
| **Anthropic SDK** | Claude API 调用 |
| **Yoga** | Flexbox 终端布局 |
| **Zod** | Schema 验证 |
| **OpenTelemetry** | 遥测/监控 |

### 目录结构总览

```
claude-code-run/
├── src/
│   ├── entrypoints/          # 入口点 (8 files)
│   │   ├── cli.tsx           # 真正的入口（shebang）
│   │   └── init.ts           # 初始化逻辑
│   ├── main.tsx              # Commander.js CLI 定义 (229KB)
│   ├── query.ts              # 核心查询循环 (68KB)
│   ├── QueryEngine.ts        # 查询引擎编排器 (47KB)
│   ├── Tool.ts               # 工具接口定义 (29KB)
│   ├── tools.ts              # 工具注册表 (17KB)
│   ├── context.ts            # 上下文构建 (6.3KB)
│   ├── tools/                # 56 个工具实现 (281 files)
│   ├── components/           # UI 组件 (593 files)
│   ├── commands/             # CLI 命令 (207 files)
│   ├── hooks/                # React Hooks (86 files)
│   ├── utils/                # 工具函数 (692 files)
│   ├── services/             # 服务层 (234 files)
│   ├── state/                # 状态管理 (7 files)
│   ├── screens/              # 屏幕组件 (3 files)
│   ├── ink/                  # 自定义 Ink 框架 (53 files)
│   ├── types/                # 类型定义 (32 files)
│   ├── constants/            # 常量 (25 files)
│   ├── bridge/               # IDE 桥接 (34 files)
│   ├── bootstrap/            # 启动状态 (4 files)
│   ├── keybindings/          # 键盘绑定 (18 files)
│   ├── migrations/           # 数据迁移 (12 files)
│   └── ...
├── packages/                 # 内部包
│   ├── @ant/                 # Anthropic 内部包（存根）
│   ├── color-diff-napi/      # 颜色差异计算
│   ├── image-processor-napi/ # 图像处理
│   └── ...
├── build.ts                  # 构建脚本
├── package.json              # 项目配置
└── tsconfig.json             # TypeScript 配置
```

---

## 第二部分：架构全景图

### 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      入口层 (Entry Layer)                    │
│  cli.tsx → init.ts → main.tsx (Commander.js)                │
├─────────────────────────────────────────────────────────────┤
│                     屏幕层 (Screen Layer)                    │
│  REPL.tsx │ ResumeConversation.tsx │ Doctor.tsx              │
├─────────────────────────────────────────────────────────────┤
│                      UI 层 (UI Layer)                       │
│  Messages │ PromptInput │ Permissions │ Dialogs │ Footer    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         自定义 Ink 渲染引擎 (Custom Ink Engine)       │   │
│  │  Reconciler │ Yoga Layout │ Frame Buffer │ ANSI      │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                    状态层 (State Layer)                      │
│  AppState Store │ Bootstrap State │ Session State            │
├─────────────────────────────────────────────────────────────┤
│                 查询引擎层 (Query Engine Layer)               │
│  QueryEngine.ts → query.ts (核心循环)                        │
│  ┌────────────┐ ┌────────────┐ ┌─────────────┐             │
│  │ 自动压缩   │ │ 微压缩     │ │ Token 预算  │             │
│  │ Autocompact│ │Microcompact│ │Token Budget │             │
│  └────────────┘ └────────────┘ └─────────────┘             │
├─────────────────────────────────────────────────────────────┤
│                   工具层 (Tool Layer)                        │
│  Tool Registry │ Tool Dispatch │ Streaming Executor         │
│  ┌────────┬────────┬────────┬────────┬────────┐            │
│  │ Bash   │ File*  │ Glob   │ Grep   │ Agent  │  ...×56   │
│  └────────┴────────┴────────┴────────┴────────┘            │
├─────────────────────────────────────────────────────────────┤
│                  权限层 (Permission Layer)                    │
│  Permission Rules │ YOLO Classifier │ Hook Gates            │
│  Modes: default │ auto │ plan │ bypass │ bubble             │
├─────────────────────────────────────────────────────────────┤
│                   API 层 (API Layer)                         │
│  claude.ts │ client.ts │ withRetry.ts │ streaming           │
│  Providers: Anthropic │ Bedrock │ Vertex │ Foundry          │
├─────────────────────────────────────────────────────────────┤
│                  服务层 (Service Layer)                      │
│  Analytics │ MCP │ Hooks │ Memory │ Session │ Config        │
├─────────────────────────────────────────────────────────────┤
│                 上下文层 (Context Layer)                      │
│  System Prompt │ CLAUDE.md │ Git Status │ User Context      │
└─────────────────────────────────────────────────────────────┘
```

### 核心数据流

```
用户输入 (stdin)
    │
    ▼
PromptInput 组件 (键盘事件处理)
    │
    ▼
REPL 屏幕 (onSubmit 回调)
    │
    ▼
QueryEngine (会话状态管理、压缩、轮次记账)
    │
    ▼
query() 核心循环 ◄──────────────────────┐
    │                                    │
    ▼                                    │
queryModel() API 调用（流式）             │
    │                                    │
    ▼                                    │
流式事件处理                              │
    │  ├── text → 渲染到 UI               │
    │  ├── thinking → 显示思考过程         │
    │  └── tool_use → 工具调度             │
    │                                    │
    ▼                                    │
工具权限检查                              │
    │  ├── allow → 执行工具               │
    │  ├── ask → 显示权限对话框            │
    │  └── deny → 返回错误                │
    │                                    │
    ▼                                    │
工具执行 (并行/串行)                      │
    │                                    │
    ▼                                    │
tool_result → messages 追加 ─────────────┘
    │
    ▼ (stop_reason === 'end_turn')
渲染最终响应 → 等待下一轮用户输入
```

---

## 第三部分：核心模块详细分析

### 3.1 入口与启动流程

#### 3.1.1 快速路径架构 (`cli.tsx`)

入口文件实现了一个**快速路径优先**的架构，在加载完整 CLI 框架之前检查特殊标志：

```
cli.tsx 执行流程:
│
├── 设置 MACRO 常量 (VERSION, BUILD_TIME, etc.)
├── 配置环境变量 (COREPACK, NODE_OPTIONS)
│
├── 快速路径检查（零导入退出）:
│   ├── --version/-v/-V
│   ├── --dump-system-prompt
│   ├── --computer-use-mcp
│   ├── --daemon-worker
│   ├── remote-control/rc/bridge
│   ├── daemon/ps/logs/attach/kill
│   ├── new/list/reply
│   ├── --update/--upgrade
│   └── --tmux --worktree
│
└── 完整路径: import main.tsx → 启动 CLI
```

**设计要点**：
- 特殊模式在加载 React 等重型依赖前直接退出
- `feature()` polyfill 始终返回 `false`（所有内部特性门控禁用）
- `globalThis.MACRO` 模拟构建时宏注入

#### 3.1.2 初始化模块 (`init.ts`)

`init()` 函数被 memo 化，只执行一次：

```
init() 执行序列:
│
├── 1. 配置与权限
│   ├── enableConfigs()
│   ├── applySafeConfigEnvironmentVariables()
│   └── applyExtraCACertsFromConfig()
│
├── 2. 关停与错误处理
│   ├── setupGracefulShutdown()
│   └── ConfigParseError 处理
│
├── 3. 后台服务初始化（fire-and-forget）
│   ├── 第一方事件日志 (OpenTelemetry)
│   ├── OAuth 账户信息
│   ├── JetBrains IDE 检测
│   └── GitHub 仓库检测
│
├── 4. 远程设置 & 策略（非阻塞）
│
├── 5. 网络配置
│   ├── configureGlobalMTLS()
│   ├── configureGlobalAgents()
│   └── preconnectAnthropicApi() (TCP+TLS 预连接)
│
└── 6. 清理注册（LSP、团队）
```

#### 3.1.3 CLI 定义 (`main.tsx`)

使用 Commander.js 定义完整 CLI，4,683 行代码。

**主要选项**：
| 选项 | 说明 |
|------|------|
| `-p, --print` | 非交互输出模式 |
| `-c, --continue` | 恢复最近对话 |
| `-r, --resume [id]` | 按 ID 恢复对话 |
| `--model <model>` | 模型覆盖 |
| `--thinking` | 思考模式 |
| `--max-turns` | 最大轮次限制 |
| `--system-prompt` | 自定义系统提示词 |
| `--mcp-config` | MCP 服务器配置 |
| `--permission-mode` | 权限模式 |
| `--dangerously-skip-permissions` | 跳过权限检查 |
| `--tools` / `--allowed-tools` | 工具管理 |
| `-w, --worktree` | Git worktree 模式 |
| `--agents` | 自定义代理 |

**子命令**：
- `mcp` — MCP 服务器管理 (serve/add/remove/list)
- `auth` — 认证管理 (login/status/logout)
- `plugin` — 插件管理 (install/uninstall/enable/disable)
- `doctor` — 诊断检查
- `update` — 更新检查
- `install` — 原生安装

**交互模式启动序列**:
```
1. 处理 CLI 选项
2. 信任对话框 & OAuth 流程
3. 服务初始化（LSP、MCP、配额检查）
4. 状态设置（加载 MCP 配置、思考模式）
5. REPL 启动
   ├── 恢复模式: 从磁盘加载对话
   ├── 直连模式: 创建远程会话
   ├── SSH 模式: 代理连接
   └── 默认模式: 构建系统提示词 → renderAndRun()
```

---

### 3.2 核心对话循环

#### 3.2.1 循环架构 (`query.ts` - 68KB)

核心是一个**无限 while(true) 循环**，通过不可变状态转换管理：

```typescript
// 伪代码 - 核心循环结构
async function* queryLoop(initialState: State) {
  let state = initialState;
  
  while (true) {
    // 1. 压缩检查
    state = await runCompaction(state);  // 自动压缩、微压缩
    
    // 2. API 调用
    const response = await* queryModelWithStreaming(state.messages);
    
    // 3. 流式处理 & 工具检测
    for await (const event of response) {
      yield event;  // 向上层传递流事件
      if (event.type === 'tool_use') collectToolBlocks(event);
    }
    
    // 4. 错误恢复（7 个 continue 点）
    if (promptTooLong)   → 压缩后 continue
    if (maxOutputTokens) → 升级到 64k 后 continue
    if (hookBlocked)     → 注入错误后 continue
    if (tokenBudget)     → +500k 后 continue
    
    // 5. 工具执行
    const toolResults = await executeTools(toolBlocks);
    
    // 6. 轮次管理
    if (stopReason === 'end_turn' && noToolUse) break;
    if (turnCount >= maxTurns) break;
    
    // 7. 状态转换（不可变）
    state = {
      messages: [...state.messages, ...assistantMsgs, ...toolResults],
      turnCount: state.turnCount + 1,
      // ... 重置恢复计数器
    };
  }
}
```

#### 3.2.2 七个 Continue 站点

| # | 触发条件 | 恢复策略 |
|---|---------|---------|
| 1 | 自动压缩成功 | yield 压缩边界，用压缩后消息继续 |
| 2 | 上下文折叠恢复 | 释放暂存的折叠，重试 |
| 3 | 反应式压缩恢复 | 全摘要压缩回退 |
| 4 | max_output_tokens 升级 | 重试使用 64k tokens |
| 5 | max_output_tokens 恢复 | 3 次尝试限制，附带 nudge 消息 |
| 6 | Hook 阻止 | 模型输出被 hook 拒绝，注入错误重新开始 |
| 7 | Token 预算继续 | +500k 自动继续（阈值 < 70%） |

#### 3.2.3 三级压缩管道

```
Stage 1: History Snip (可选)
  └── 移除最旧消息，释放 token

Stage 2: Microcompaction (每轮执行)
  └── 应用 prompt 缓存编辑

Stage 3: Autocompaction (反应式)
  └── 当 token 数超阈值时触发
  └── 生成摘要消息替换原始消息
```

#### 3.2.4 QueryEngine 编排器 (`QueryEngine.ts` - 47KB)

比 `query()` 更高层的编排器：

```
QueryEngine 职责:
├── 会话状态管理（消息历史）
├── 文件历史快照
├── 归因追踪
├── 轮次级记账
├── 用户消息注入
├── 命令队列处理
└── 压缩策略协调
```

---

### 3.3 API 层与流式处理

#### 3.3.1 API 客户端 (`services/api/claude.ts`)

**请求构建流程**：
```
1. paramsFromContext() — 构建请求参数
   ├── 系统提示词
   ├── 消息数组（含工具结果）
   ├── 工具定义（JSON Schema）
   ├── Beta 头部注入
   ├── 思考模式配置
   └── 努力级别配置

2. 创建 SDK 客户端（按 Provider）
   ├── Anthropic Direct: API key
   ├── AWS Bedrock: AWS credentials
   ├── Google Vertex: Google auth
   └── Azure Foundry: Internal auth

3. 发起流式请求
   └── sdk.beta.messages.stream(params)
```

#### 3.3.2 流式事件处理

```
事件类型:
├── message_start     → 初始化 partialMessage，基线 token 用量
├── content_block_start → 分配内容块（text/tool_use/thinking）
├── content_block_delta → 增量累积（文本追加、JSON 拼接）
├── content_block_stop  → yield AssistantMessage（首次可观察输出）
├── message_delta      → 更新 usage + stop_reason（引用式变异）
└── message_stop       → 流完成
```

**关键设计：引用式变异**
- `message_delta` 通过直接属性赋值修改消息对象
- 转录写入队列持有同一引用
- 延迟 100ms 刷新确保变异到达后再序列化

#### 3.3.3 多 Provider 支持

| 方面 | Anthropic | Bedrock | Vertex | Foundry |
|------|-----------|---------|--------|---------|
| 认证 | API Key | AWS Credentials | Google Auth | Internal |
| Beta 头 | `betas` 数组 | `extraBodyParams` | `betas` 数组 | `betas` 数组 |
| 缓存编辑 | 支持 | 不支持 | 不支持 | 不支持 |
| 1h 缓存 TTL | 门控 | 环境变量 | 不支持 | 门控 |
| 努力级别 | output_config | 模型覆盖 | output_config | output_config |

Provider 选择逻辑：
```
CLAUDE_CODE_USE_BEDROCK=true  → 'bedrock'
CLAUDE_CODE_USE_VERTEX=true   → 'vertex'
CLAUDE_CODE_USE_FOUNDRY=true  → 'foundry'
默认                          → 'firstParty'
```

#### 3.3.4 双模式工具执行

**模式 1: 流式工具执行器 (StreamingToolExecutor)**
- 在模型还在流式输出时**并发执行**已完成的工具块
- 降低端到端延迟

**模式 2: 顺序执行（回退）**
- 等待完整模型响应后批量执行
- 更简单，用于回退场景

---

### 3.4 工具系统

#### 3.4.1 工具接口 (`Tool.ts` - 29KB)

核心 `Tool<Input, Output, ProgressData>` 泛型接口：

```typescript
interface Tool<I, O, P> {
  // === 必需属性 ===
  name: string;
  inputSchema: ZodSchema<I>;                // Zod Schema 输入验证
  
  // === 核心方法 ===
  call(args, context, canUseTool, parentMsg, onProgress): Promise<ToolResult<O>>;
  description(input, options): string;       // 生成工具描述给模型
  prompt(options): string;                   // 工具使用指令
  checkPermissions(input, context): PermissionResult;
  validateInput(input, context): ValidationResult;
  
  // === 能力声明 ===
  isConcurrencySafe(input): boolean;         // 是否支持并发（默认 false）
  isReadOnly(input): boolean;                // 只读操作（默认 false）
  isDestructive(input): boolean;             // 破坏性操作
  isEnabled(): boolean;                      // 运行时启用门控
  
  // === UI 渲染 ===
  renderToolUseMessage(input, options): ReactNode;
  renderToolResultMessage(output, progress, options): ReactNode;
  renderToolUseErrorMessage(result, options): ReactNode;
  renderToolUseRejectedMessage(input, options): ReactNode;
  renderGroupedToolUse(toolUses, options): ReactNode;
  getToolUseSummary(input): string;
  getActivityDescription(input): string;     // Spinner 显示文本
  
  // === 高级特性 ===
  shouldDefer: boolean;                      // 延迟加载（ToolSearch 发现）
  isMcp: boolean;                            // MCP 工具标记
  interruptBehavior(): 'cancel' | 'block';   // 中断行为
  maxResultSizeChars: number;                // 结果持久化阈值
}

type ToolResult<T> = {
  data: T;
  newMessages?: Message[];                   // 注入额外消息
  contextModifier?: (ctx) => ctx;            // 修改工具上下文
  mcpMeta?: { _meta?, structuredContent? };  // MCP 透传
};
```

#### 3.4.2 完整工具清单（56 个）

**核心 I/O 工具（始终启用）**：
| 工具 | 功能 | 只读 | 并发安全 |
|------|------|------|---------|
| `BashTool` | Shell 命令执行 | 否 | 否 |
| `FileReadTool` | 文件读取（支持 PDF/图片） | 是 | 是 |
| `FileEditTool` | 文件原地编辑（字符串替换） | 否 | 否 |
| `FileWriteTool` | 文件创建/覆盖 | 否 | 否 |
| `GlobTool` | 文件模式搜索 | 是 | 是 |
| `GrepTool` | 内容正则搜索 | 是 | 是 |
| `NotebookEditTool` | Jupyter 笔记本编辑 | 否 | 否 |

**网络 & 搜索工具**：
| 工具 | 功能 |
|------|------|
| `WebFetchTool` | URL 内容获取与处理 |
| `WebSearchTool` | 网络搜索 |

**代理 & 任务管理工具**：
| 工具 | 功能 |
|------|------|
| `AgentTool` | 子代理生成（含内置代理类型） |
| `TaskCreateTool` | 创建任务 |
| `TaskGetTool` | 获取任务 |
| `TaskUpdateTool` | 更新任务 |
| `TaskListTool` | 列出任务 |
| `TaskStopTool` | 停止任务 |
| `TaskOutputTool` | 获取子代理输出 |

**交互 & 规划工具**：
| 工具 | 功能 |
|------|------|
| `AskUserQuestionTool` | 向用户提问 |
| `EnterPlanModeTool` | 进入规划模式 |
| `ExitPlanModeTool` | 退出规划模式 |
| `SkillTool` | 执行技能/提示词 |
| `BriefTool` | 发送用户消息 |

**扩展工具**：
| 工具 | 功能 | 门控条件 |
|------|------|---------|
| `ToolSearchTool` | 搜索可用工具 | isToolSearchEnabled |
| `MCPTool` | MCP 服务器资源访问 | MCP 客户端存在 |
| `EnterWorktreeTool` | 创建隔离 git worktree | isWorktreeMode |
| `ExitWorktreeTool` | 清理 worktree | isWorktreeMode |
| `CronCreateTool` | 定时任务创建 | 始终 |
| `CronDeleteTool` | 定时任务删除 | 始终 |
| `CronListTool` | 定时任务列表 | 始终 |
| `RemoteTriggerTool` | 远程代理触发 | AGENT_TRIGGERS_REMOTE |
| `SendMessageTool` | 向队友发消息 | Agent Swarms |
| `TeamCreateTool` | 创建代理团队 | Agent Swarms |
| `TeamDeleteTool` | 删除代理团队 | Agent Swarms |
| `SleepTool` | 调度延迟 | PROACTIVE/KAIROS |
| `LSPTool` | LSP 集成 | ENABLE_LSP_TOOL |
| `PowerShellTool` | PowerShell 执行 | isPowerShellTool |
| `REPLTool` | 交互式 VM Shell | ANT-only |
| `MonitorTool` | 监控工具执行 | MONITOR_TOOL |
| `WebBrowserTool` | 浏览器自动化 | WEB_BROWSER_TOOL |

#### 3.4.3 工具注册与装配

```
getAllBaseTools()           ← 返回所有工具（含门控判断）
       │
       ▼
getTools(permCtx)          ← 按权限 deny 规则过滤
       │                      ← 按模式过滤（Simple/REPL）
       ▼
assembleToolPool(permCtx, mcpTools)  ← 合并内置 + MCP 工具
       │                                ← 按名称去重（内置优先）
       │                                ← 排序（缓存稳定性）
       ▼
最终工具列表 → 注入到 API 请求
```

#### 3.4.4 工具执行上下文 (ToolUseContext)

```typescript
type ToolUseContext = {
  options: {
    tools: Tool[];
    commands: Command[];
    model: string;
    mcpClients: MCPConnection[];
    featureFlags: Record<string, boolean>;
  };
  abortController: AbortController;        // 取消支持
  readFileState: LRUCache;                  // 文件读取缓存
  getAppState(): AppState;                  // 获取会话状态
  setAppState(updater): void;               // 修改会话状态
  setToolJSX?(jsx): void;                   // UI 更新回调
  requestPrompt?(factory): void;            // 交互式提示
  toolDecisions?: Map<string, Decision>;    // 工具决策缓存
};
```

---

### 3.5 权限系统

#### 3.5.1 权限模式

| 模式 | 行为 | 场景 |
|------|------|------|
| `default` | 询问所有操作 | 交互式默认 |
| `auto` | 自动批准安全操作 | 安全分类器 |
| `plan` | 用户写计划，Claude 执行 | 规划模式 |
| `bypass` | 全部批准（危险） | 开发调试 |
| `bubble` | 内部：auto + 用户提示抑制 | 后台代理 |

#### 3.5.2 权限规则结构

```typescript
type PermissionRule = {
  source: 'userSettings' | 'projectSettings' | 'localSettings' |
          'flagSettings' | 'policySettings' | 'cliArg' | 'command' | 'session';
  ruleBehavior: 'allow' | 'deny' | 'ask';
  ruleValue: {
    toolName: string;     // 如 "Bash", "FileEdit"
    ruleContent?: string; // 如 "git *", "/path/to/file"
  };
};
```

#### 3.5.3 权限检查流程

```
工具调用触发
    │
    ▼
1. validateInput(input, context)
    │  └── 输入格式验证
    ▼
2. tool.checkPermissions(input, context)
    │  └── 工具特定权限逻辑
    ▼
3. hasPermissionsToUseTool() — 通用权限系统
    │  ├── 3a. 规则匹配（allow/deny/ask 规则）
    │  ├── 3b. 模式决策（按当前模式判断）
    │  ├── 3c. 分类器检查（async，安全评估）
    │  └── 3d. 拒绝追踪（阈值后自动升级为 ask）
    ▼
4. PreToolUse Hook 执行
    │  └── 用户定义的 shell 命令
    ▼
5. 最终决策
    ├── allow → 执行工具
    ├── ask   → 显示权限对话框 → 用户决策
    └── deny  → 返回错误消息
```

#### 3.5.4 权限决策类型

```typescript
// 允许
{ behavior: 'allow', updatedInput?, decisionReason? }

// 询问（触发 UI 对话框）
{ behavior: 'ask', message, suggestions?, pendingClassifierCheck? }

// 拒绝
{ behavior: 'deny', message, decisionReason }

// 决策原因
type DecisionReason =
  | { type: 'rule', rule: PermissionRule }
  | { type: 'mode', mode: PermissionMode }
  | { type: 'hook', hookName, reason? }
  | { type: 'asyncAgent', reason }
```

---

### 3.6 UI 层与终端渲染

#### 3.6.1 自定义 Ink 渲染引擎 (`src/ink/`)

这不是开源 Ink 库，而是 Claude Code 自己的终端 React 渲染器（53 个文件）：

```
渲染管道:
│
├── React Reconciler (自定义)
│   └── 创建/更新/删除 DOM 元素
│   └── 附加/分离 Yoga 布局节点
│
├── Yoga Layout Engine
│   └── Flexbox 布局计算
│   └── 支持: flexDirection, width, height, padding, margin, gap, flex
│
├── Frame Buffer (双缓冲)
│   ├── frontFrame — 当前显示
│   └── backFrame  — 渲染中
│
├── Render Pipeline
│   1. Yoga 布局计算 (calculateLayout)
│   2. DOM → Buffer 绘制 (renderNodeToOutput)
│   3. 叠加层应用（选择、搜索高亮）
│   4. 差异计算 + 写入终端 (writeDiffToTerminal)
│   5. 交换缓冲区
│
├── 输入处理
│   └── stdin → parseKeypress → KeyboardEvent → 事件分发
│
└── 性能优化
    ├── 60 FPS 节流 (16.67ms/帧)
    ├── ANSI 代码池化 (StylePool)
    ├── 字符串驻留 (CharPool)
    └── 选择性重绘
```

#### 3.6.2 组件层级

```
App (根 Provider)
├── AppStateProvider (会话状态)
│   ├── StatsProvider (性能指标)
│   │   ├── FpsMetricsProvider
│   │   │   └── REPL (主屏幕, 5002 行)
│   │   │       ├── LogoHeader
│   │   │       ├── Messages / VirtualMessageList
│   │   │       │   └── MessageRow
│   │   │       │       ├── UserMessage (文本 + 图片)
│   │   │       │       ├── AssistantMessage (文本 + 工具调用 + 思考)
│   │   │       │       ├── SystemMessage
│   │   │       │       ├── GroupedToolUseContent (折叠优化)
│   │   │       │       └── CollapsedReadSearchContent
│   │   │       ├── PermissionRequest (浮动)
│   │   │       │   ├── BashPermissionRequest
│   │   │       │   ├── FileEditPermissionRequest (含 diff 预览)
│   │   │       │   ├── FileWritePermissionRequest
│   │   │       │   ├── WebFetchPermissionRequest
│   │   │       │   └── FallbackPermissionRequest
│   │   │       ├── SpinnerWithVerb
│   │   │       ├── TaskListV2 (展开时)
│   │   │       ├── PromptInput
│   │   │       │   ├── TextInput / VimTextInput
│   │   │       │   ├── PromptInputModeIndicator
│   │   │       │   ├── PromptInputQueuedCommands
│   │   │       │   └── PromptInputFooter
│   │   │       └── 各种 Dialog (模型选择、退出等)
```

#### 3.6.3 虚拟滚动 (VirtualMessageList)

对于长对话（2000+ 消息），使用虚拟化渲染：

```
优化策略:
├── 高度缓存: UUID + 终端宽度 → 行高
├── 增量 key 数组: 只追加，不重建
├── 仅渲染可见项 + 小缓冲区
├── 搜索索引预热: 预先小写化所有消息
├── 粘性提示跟踪: 滚动时输入框浮动
└── 选择性测量: 只测量已挂载元素
```

#### 3.6.4 消息渲染流程

```
原始 API 消息
    │
    ▼
normalizeMessages()     ← 标准化 + 去重
    │
    ▼
applyGrouping()         ← 折叠连续工具调用
    │
    ▼
filterForBriefTool()    ← Brief 模式过滤（可选）
    │
    ▼
buildMessageLookups()   ← 构建查找表
    │
    ▼
渲染策略选择
├── 全屏模式: VirtualMessageList (虚拟化)
└── 普通模式: .map() (直接渲染)
```

---

### 3.7 状态管理

#### 3.7.1 Store 模式 (`state/store.ts`)

简洁的不可变状态容器 + 发布/订阅：

```typescript
type Store<T> = {
  getState: () => T;
  setState: (updater: (prev: T) => T) => void;
  subscribe: (listener: () => void) => () => void;
};
```

特点：
- `Object.is` 浅相等阻止不必要通知
- 可选 `onChange` 回调处理副作用
- 类似 Zustand 但更轻量

#### 3.7.2 AppState 结构（核心字段）

```typescript
type AppState = {
  // 渲染状态
  statusLineText: string | undefined;
  expandedView: 'none' | 'tasks' | 'teammates';
  isBriefOnly: boolean;
  
  // 模型 & 工具权限
  mainLoopModel: ModelSetting;
  toolPermissionContext: ToolPermissionContext;
  
  // 会话
  settings: SettingsJson;
  initialMessage: { message: UserMessage; ... } | null;
  
  // 任务 & 后台
  tasks: { [taskId: string]: TaskState };      // 可变
  agentNameRegistry: Map<string, AgentId>;
  foregroundedTaskId?: string;
  
  // MCP & 插件
  mcp: {
    clients: MCPServerConnection[];
    tools: Tool[];
    commands: Command[];
    resources: Record<string, ServerResource[]>;
  };
  plugins: { enabled: LoadedPlugin[]; disabled: LoadedPlugin[]; ... };
  
  // 功能标志
  thinkingEnabled: boolean | undefined;
  fastMode?: boolean;
  
  // 远程 & 桥接
  remoteSessionUrl?: string;
  remoteConnectionStatus: 'connecting' | 'connected' | ...;
  replBridgeEnabled: boolean;
  
  // 50+ 更多字段...
};
```

#### 3.7.3 React Hooks 消费

```typescript
// 订阅状态切片（仅在切片变化时重渲染）
function useAppState<R>(selector: (state: AppState) => R): R;

// 获取 setState（不触发重渲染）
function useSetAppState(): (updater: (prev: AppState) => AppState) => void;
```

#### 3.7.4 副作用处理 (`onChangeAppState.ts`)

所有 AppState 变更的单一副作用入口：
- 权限模式变更 → 通知 CCR (web UI) + SDK
- 模型变更 → 持久化到设置
- 配置变更 → 持久化到磁盘
- 认证缓存失效

#### 3.7.5 启动状态 (`bootstrap/state.ts`)

全局单例状态（非 React）：
- `sessionId` — 会话 ID
- `cwd` / `originalCwd` / `projectRoot`
- `modelUsage` — 每模型 token 用量
- `totalCostUSD` — 累计费用
- `registeredHooks` — 活跃 hook 回调
- OpenTelemetry 仪表盘

---

### 3.8 上下文与系统提示词

#### 3.8.1 系统提示词构建

**分层组合系统**：

```
优先级（从高到低）:
├── Override（最高）: 显式设置的系统提示词
├── Coordinator: 协调器模式提示词
├── Agent: 代理专用提示词
├── Custom: --system-prompt 用户提供
├── Default: 标准 Claude Code 提示词
└── Append: 追加提示词后缀
```

**动态段落**（`constants/prompts.ts` - 54KB）：
- 介绍段
- 系统指令
- 任务执行指南
- 工具执行安全准则
- 工具可用性信息
- MCP 服务器指令
- 语言偏好
- 输出风格配置
- Hooks 文档
- 系统提醒

**缓存优化**：
- `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 标记分隔可缓存静态内容与动态内容
- 日期 memo 化到 `getSessionStartDate()`（每会话仅变更一次）
- 防止午夜缓存失效

#### 3.8.2 CLAUDE.md 加载 (`utils/claudemd.ts` - 1,479 行)

**记忆层级**（优先级从低到高）：
1. **托管记忆**: `/etc/claude-code/CLAUDE.md` (全局，所有用户)
2. **用户记忆**: `~/.claude/CLAUDE.md` (私有，全局)
3. **项目记忆**: `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md`
4. **本地记忆**: `CLAUDE.local.md` (私有，项目专用)
5. **自动记忆**: MEMORY.md 文件（截断）
6. **团队记忆**: 团队级指令

**高级特性**：
- `@include` 指令：引用其他文件
- YAML frontmatter 解析：`paths:` glob 模式匹配
- HTML 注释剥离
- 二进制文件过滤
- 循环引用防护
- 40,000 字符推荐上限

#### 3.8.3 上下文构建 (`context.ts`)

```typescript
// 系统级上下文（memo 化）
function getSystemContext(): string {
  // Git 状态
  // 可选缓存断路器注入
}

// 用户级上下文（memo 化）
function getUserContext(): string {
  // CLAUDE.md 文件内容
  // 当前日期
}
```

---

### 3.9 Hooks 系统

#### 3.9.1 架构 (`utils/hooks.ts` - 5,121 行)

用户定义的 shell 命令，在生命周期事件处触发：

**Hook 事件**：
| 事件 | 触发时机 |
|------|---------|
| `PreToolUse` | 工具执行前（权限检查点） |
| `PostToolUse` | 工具完成后 |
| `SessionStart` | 会话初始化 |
| `Setup` | 初始设置 |
| `SubagentStart` | 子代理生成 |
| `FileChanged` | 文件系统变更 |
| `UserPromptSubmit` | 用户消息提交 |

**Hook 响应 Schema**：
```typescript
{
  continue?: boolean;          // false 停止执行
  decision?: 'approve' | 'block';  // 权限裁决
  reason?: string;
  systemMessage?: string;
  hookSpecificOutput?: {
    permissionDecision?: 'allow' | 'ask' | 'deny';
    updatedInput?: Record<string, unknown>;
    additionalContext?: string;
  };
}
```

**配置方式**：在 `.claude/settings.json` 中定义

---

### 3.10 会话持久化

#### 3.10.1 会话存储 (`utils/sessionStorage.ts` - 5,106 行)

**存储内容**：
- 完整消息历史
- 工具使用结果（大结果持久化到磁盘）
- 文件历史快照
- 归因追踪数据
- 会话元数据（模型、token 用量、费用）

**存储位置**：`~/.claude/sessions/<session-id>/`

**会话恢复**：
- `--continue` — 恢复最近对话
- `--resume <id>` — 按 ID 恢复
- `--from-pr` — 从 PR 关联的会话恢复

#### 3.10.2 文件历史 (`utils/fileHistory.ts` - 1,115 行)

追踪每个被修改文件的变更历史：
- 原始内容快照
- 各次编辑的 diff
- 归因状态（用于 commit 追踪）

---

### 3.11 MCP 协议集成

#### 3.11.1 MCP 服务

**服务层** (`services/mcp/`)：
- 服务器连接管理
- 资源发现与访问
- 工具注册到 Claude 工具池

**工具层**：
- `MCPTool` — MCP 工具的执行包装器
- `ReadMcpResourceTool` — 读取 MCP 资源
- `ListMcpResourcesTool` — 列出 MCP 资源
- `McpAuthTool` — MCP 认证

**配置方式**：
- `--mcp-config` CLI 参数
- `.claude/settings.json` 中的 `mcpServers`
- Claude Desktop 导入

---

### 3.12 子代理系统

#### 3.12.1 AgentTool 架构 (`tools/AgentTool/` - 18 files)

**内置代理类型**：
| 代理 | 用途 |
|------|------|
| `general-purpose` | 通用多步骤任务 |
| `Explore` | 快速代码库探索 |
| `Plan` | 实现计划设计 |
| `claude-code-guide` | Claude Code 使用指南 |
| `large-file-summarizer` | 大文件分析 |

**子代理执行**：
- 每个子代理获得独立的 query 循环
- 权限链路可级联到父级
- 支持 worktree 隔离（独立仓库副本）
- 支持后台运行 (`run_in_background`)
- 进度通过 `AgentToolProgress` 流式传递

#### 3.12.2 任务管理

```
TaskCreate → 创建任务记录
TaskGet    → 获取任务状态
TaskUpdate → 更新任务（完成/失败）
TaskList   → 列出所有任务
TaskStop   → 停止运行中的任务
TaskOutput → 获取子代理输出
```

#### 3.12.3 团队/群集 (Agent Swarms)

```
TeamCreate → 创建代理团队
TeamDelete → 删除代理团队
SendMessage → 向队友发消息
ListPeers → 列出群集对等体
```

通过 Unix Domain Socket (UDS) 实现进程间通信。

---

## 第四部分：技术栈与依赖

### 核心依赖

| 类别 | 包 | 用途 |
|------|-----|------|
| **运行时** | Bun >= 1.2.0 | JavaScript 运行时 + 构建工具 |
| **框架** | React 19.2.4 | UI 组件模型 |
| **CLI** | Commander.js | 命令行参数解析 |
| **AI SDK** | @anthropic-ai/sdk | Claude API 调用 |
| **Agent SDK** | @anthropic-ai/claude-agent-sdk | 代理构建 |
| **云 SDK** | AWS Bedrock, Google Vertex, Azure | 多 Provider 支持 |
| **Schema** | Zod | 输入验证 |
| **样式** | Chalk | 终端颜色 |
| **布局** | Yoga (via react-reconciler) | Flexbox 终端布局 |
| **文件** | Sharp | 图像处理 |
| **Markdown** | Marked, Turndown | Markdown 解析/HTML→MD |
| **代码高亮** | highlight.js | 语法高亮 |
| **遥测** | OpenTelemetry | 指标、日志、追踪 |
| **类型** | TypeScript 6.0.2 | 类型检查 |
| **Lint** | Biome 2.4.10 | 代码质量 |

### 构建配置

```typescript
// build.ts - 自定义 Bun 代码分割构建
bun build src/entrypoints/cli.tsx --outdir dist --target bun
// 输出: dist/cli.js (~25MB) + chunk files
```

---

## 第五部分：复刻实施计划

### 总体策略

采用**渐进式构建**策略，每个 Phase 产出可运行、可测试的增量成果。从最核心的 CLI + API 循环开始，逐步叠加功能层。

### 技术选型建议

| 层 | 推荐 | 备选 |
|----|------|------|
| 运行时 | Bun | Node.js (需调整构建) |
| 语言 | TypeScript | - |
| CLI 框架 | Commander.js | yargs, oclif |
| UI 框架 | Ink (开源版) | 自定义终端渲染 |
| API SDK | @anthropic-ai/sdk | 直接 HTTP 调用 |
| 状态管理 | Zustand 或自定义 Store | Redux, Jotai |
| Schema | Zod | joi, yup |

---

### Phase 1: 基础骨架（MVP）

> 目标：能发送消息到 Claude API 并获得流式响应

**预计复杂度**：⭐⭐ | **交付物**：可用的 pipe 模式

#### 1.1 项目初始化
```
├── package.json (Bun workspace)
├── tsconfig.json (ESNext, react-jsx)
├── src/
│   ├── entrypoints/
│   │   └── cli.tsx          # 入口点 + 全局常量
│   ├── main.tsx             # Commander.js 基础定义
│   └── types/
│       ├── message.ts       # 消息类型定义
│       └── global.d.ts      # 全局类型
```

#### 1.2 API 层 (最小)
```
src/services/api/
├── claude.ts         # API 调用 + 流式处理
├── client.ts         # SDK 客户端创建
└── errors.ts         # 错误处理
```

核心实现：
- `queryModel()` 异步生成器：构建请求 → 流式响应 → yield 事件
- 事件类型处理：`message_start`, `content_block_delta`, `content_block_stop`, `message_delta`
- 支持 Anthropic Direct Provider
- API key 认证

#### 1.3 最小查询循环
```
src/
├── query.ts          # 简化版核心循环（无压缩/恢复）
└── context.ts        # 基础系统提示词
```

核心实现：
- 单轮 API 调用 + 响应输出
- 基础系统提示词（静态）
- `-p/--print` pipe 模式

#### 1.4 验收标准
- `echo "hello" | bun run src/entrypoints/cli.tsx -p` 能获得 Claude 响应
- 流式输出到 stdout
- 支持 `--model` 参数

---

### Phase 2: 核心工具链

> 目标：实现文件操作和 Shell 执行

**预计复杂度**：⭐⭐⭐ | **交付物**：能执行工具的 pipe 模式

#### 2.1 工具接口
```
src/
├── Tool.ts           # Tool 接口定义（精简版）
│                     # name, inputSchema, call(), description(), checkPermissions()
└── tools.ts          # 工具注册表
```

#### 2.2 核心工具实现
```
src/tools/
├── BashTool/
│   ├── index.ts      # Shell 命令执行
│   ├── schema.ts     # 输入 schema (command, timeout, description)
│   └── utils.ts      # Shell 检测、命令过滤
├── FileReadTool/
│   ├── index.ts      # 文件读取（含行号）
│   └── schema.ts     # 输入 schema (file_path, offset, limit)
├── FileEditTool/
│   ├── index.ts      # 字符串替换编辑
│   └── schema.ts     # 输入 schema (file_path, old_string, new_string)
├── FileWriteTool/
│   ├── index.ts      # 文件创建/覆盖
│   └── schema.ts
├── GlobTool/
│   ├── index.ts      # 文件模式搜索
│   └── schema.ts
└── GrepTool/
    ├── index.ts       # 内容正则搜索 (ripgrep)
    └── schema.ts
```

#### 2.3 工具调度循环
升级 `query.ts`：
- 检测 `tool_use` 内容块
- 查找并执行对应工具
- 将 `tool_result` 追加到消息数组
- 循环直到 `stop_reason === 'end_turn'`

#### 2.4 验收标准
- Claude 能自主调用 Bash、读写文件
- 工具结果正确回传给模型
- 多轮工具调用循环正常

---

### Phase 3: 交互式 REPL

> 目标：实现终端交互界面

**预计复杂度**：⭐⭐⭐⭐ | **交付物**：交互式 CLI

#### 3.1 终端 UI 基础
```
src/
├── ink.ts            # Ink 渲染包装
├── ink/              # 使用开源 Ink 或自定义
│   └── ...
├── components/
│   ├── App.tsx       # 根 Provider
│   ├── Messages.tsx  # 消息列表
│   ├── MessageRow.tsx # 单条消息
│   └── PromptInput/
│       ├── PromptInput.tsx    # 输入框
│       ├── TextInput.tsx      # 文本输入
│       └── Footer.tsx         # 底部状态栏
└── screens/
    └── REPL.tsx      # 主 REPL 屏幕
```

#### 3.2 状态管理
```
src/state/
├── store.ts          # 轻量 Store (get/set/subscribe)
├── AppState.tsx      # Provider + useAppState hook
└── AppStateStore.ts  # 类型定义
```

#### 3.3 消息渲染
- 用户消息（文本 + 图片引用）
- 助手消息（文本 + 思考 + 工具调用）
- 系统消息
- 工具调用进度显示（Spinner）
- Markdown 渲染

#### 3.4 输入处理
- 文本输入 + 光标管理
- 历史记录（上下键）
- 多行输入（Shift+Enter 或自动检测）
- Ctrl+C 中断当前请求
- Ctrl+D 退出

#### 3.5 验收标准
- 交互式对话可正常进行
- 流式响应实时显示
- 工具调用有可视化反馈
- 基础键盘快捷键工作

---

### Phase 4: 对话管理与持久化

> 目标：支持对话历史与恢复

**预计复杂度**：⭐⭐⭐ | **交付物**：可持久化的对话

#### 4.1 会话存储
```
src/utils/
├── sessionStorage.ts  # 会话持久化
│   ├── saveSession()
│   ├── loadSession()
│   └── listSessions()
└── history.ts        # 对话历史管理
```

存储结构：`~/.claude/sessions/<uuid>/`

#### 4.2 压缩系统
```
src/services/compact/
├── autocompact.ts    # 自动压缩（token 阈值触发）
├── microcompact.ts   # 微压缩（每轮缓存编辑）
└── summary.ts        # 摘要生成
```

#### 4.3 QueryEngine 实现
```
src/QueryEngine.ts    # 高级编排器
├── 消息历史管理
├── 压缩策略协调
├── 轮次管理 (maxTurns)
├── Token 预算追踪
└── 文件历史快照
```

#### 4.4 CLI 选项
- `--continue` / `-c` — 恢复最近对话
- `--resume <id>` / `-r` — 按 ID 恢复
- `--max-turns` — 最大轮次

#### 4.5 验收标准
- 对话自动保存到磁盘
- `--continue` 能恢复上次对话
- Token 超阈值自动压缩
- 长对话不会 OOM

---

### Phase 5: 权限与安全

> 目标：实现完整的权限控制

**预计复杂度**：⭐⭐⭐⭐ | **交付物**：安全的工具执行

#### 5.1 权限框架
```
src/utils/permissions/
├── permissions.ts     # 权限检查核心逻辑
├── rules.ts          # 规则匹配
├── modes.ts          # 权限模式定义
└── classifier.ts     # 安全分类器（可选）
```

#### 5.2 权限 UI
```
src/components/permissions/
├── PermissionRequest.tsx          # 权限对话框分发器
├── BashPermissionRequest.tsx      # Bash 命令权限
├── FileEditPermissionRequest.tsx  # 文件编辑权限（含 diff）
├── FileWritePermissionRequest.tsx # 文件写入权限
└── FallbackPermissionRequest.tsx  # 通用权限
```

#### 5.3 权限模式
- `default` — 询问所有操作
- `plan` — 规划模式（限制执行）
- `bypass` — 全批准（需确认）

#### 5.4 权限规则
- `alwaysAllowRules` — 白名单
- `alwaysDenyRules` — 黑名单
- 持久化到 `.claude/settings.json`
- 支持工具名 + 内容模式匹配

#### 5.5 验收标准
- Bash 命令执行前需用户确认
- 文件写入显示 diff 预览
- 可通过设置配置永久允许/拒绝规则
- Shift+Tab 可切换权限模式

---

### Phase 6: 高级功能

> 目标：完善用户体验

**预计复杂度**：⭐⭐⭐⭐ | **交付物**：功能完备的 CLI

#### 6.1 CLAUDE.md 系统
```
src/utils/claudemd.ts  # 发现 + 加载 CLAUDE.md 层级
├── 递归向上遍历目录
├── 多层优先级合并
├── @include 指令解析
└── Frontmatter 解析（paths 过滤）
```

#### 6.2 Git 集成
```
src/utils/
├── git.ts            # Git 状态、分支检测
├── gitDiff.ts        # Diff 处理
└── commitAttribution.ts  # 变更归因
```

#### 6.3 Hooks 系统
```
src/utils/hooks.ts    # 用户定义的 shell hook
├── Hook 事件: PreToolUse, PostToolUse, SessionStart, etc.
├── 配置: .claude/settings.json
├── 输出捕获 + 权限集成
└── 超时控制 (10 min default)
```

#### 6.4 Thinking 模式
```
src/utils/thinking.ts
├── enabled / adaptive / disabled
├── Extended thinking blocks 渲染
└── token 配额管理
```

#### 6.5 多 Provider 支持
```
src/utils/model/providers.ts
├── Anthropic Direct
├── AWS Bedrock
├── Google Vertex
└── 环境变量检测 + 自动切换
```

#### 6.6 工具搜索 (ToolSearch)
```
src/tools/ToolSearchTool/
├── 延迟加载工具的发现
├── 关键词匹配 + 语义搜索
└── 按需加载 Schema
```

#### 6.7 其他工具
- `WebFetchTool` — URL 内容获取
- `WebSearchTool` — 网络搜索
- `NotebookEditTool` — Jupyter 编辑
- `AskUserQuestionTool` — 向用户提问

#### 6.8 验收标准
- CLAUDE.md 正确加载和合并
- Git 状态集成到系统提示词
- Hooks 能在工具执行前/后触发
- 思考模式正常显示

---

### Phase 7: 扩展生态

> 目标：支持子代理、MCP、命令系统

**预计复杂度**：⭐⭐⭐⭐⭐ | **交付物**：可扩展的平台

#### 7.1 子代理系统 (AgentTool)
```
src/tools/AgentTool/
├── index.ts          # 子代理生成与管理
├── agents.ts         # 内置代理类型定义
├── worktree.ts       # Git worktree 隔离
└── background.ts     # 后台运行支持

内置代理:
├── general-purpose   # 通用多步骤
├── Explore           # 代码库探索
├── Plan             # 方案设计
└── large-file-summarizer  # 大文件分析
```

#### 7.2 任务系统
```
src/tools/
├── TaskCreateTool/
├── TaskGetTool/
├── TaskUpdateTool/
├── TaskListTool/
├── TaskStopTool/
└── TaskOutputTool/

src/tasks/            # 任务执行器
└── runner.ts
```

#### 7.3 MCP 集成
```
src/services/mcp/
├── client.ts         # MCP 客户端连接管理
├── tools.ts          # MCP 工具注册
├── resources.ts      # 资源发现
└── auth.ts           # OAuth 认证

CLI:
├── mcp serve         # 启动 MCP 服务器
├── mcp add           # 添加 MCP 服务器
├── mcp remove        # 移除 MCP 服务器
└── mcp list          # 列出 MCP 服务器
```

#### 7.4 命令系统 (Slash Commands)
```
src/commands/
├── help/             # /help
├── commit/           # /commit
├── config/           # /config
├── memory/           # /memory
├── context/          # /context
├── model/            # /model
├── hooks/            # /hooks
├── exit/             # /exit
└── ...

src/commands.ts       # 命令注册表
```

#### 7.5 Skills 系统
```
src/skills/
├── loader.ts         # 技能加载
├── bundler.ts        # 技能打包
└── registry.ts       # 技能注册
```

#### 7.6 验收标准
- 子代理能独立执行复杂任务
- MCP 服务器可连接并提供工具
- Slash 命令正常工作
- 任务可创建/追踪/完成

---

### Phase 8: 生产化

> 目标：性能优化、遥测、稳定性

**预计复杂度**：⭐⭐⭐ | **交付物**：生产就绪的 CLI

#### 8.1 性能优化
- 虚拟滚动 (VirtualMessageList)
- 流式工具执行 (StreamingToolExecutor)
- API 预连接 (preconnectAnthropicApi)
- 延迟工具加载 (shouldDefer + ToolSearch)
- 60 FPS 渲染节流
- 双缓冲终端输出

#### 8.2 错误恢复
- prompt-too-long 自动压缩恢复
- max_output_tokens 升级重试
- Hook 阻止后重启
- Token 预算自动继续
- 网络断连重试 (withRetry)

#### 8.3 遥测与监控
```
src/utils/telemetry/
├── metrics.ts        # 指标收集
├── traces.ts         # 追踪
└── logs.ts           # 日志

src/utils/
├── cost-tracker.ts   # 费用追踪
├── stats.ts          # 会话统计
└── queryProfiler.ts  # 查询性能分析
```

#### 8.4 构建与分发
```
build.ts              # Bun 代码分割构建
├── 输出: dist/cli.js (~25MB)
├── target: bun
└── code-splitting: 按需加载
```

#### 8.5 IDE 桥接（可选）
```
src/bridge/
├── Bridge 通信协议
├── VS Code 集成
└── JetBrains 集成
```

#### 8.6 Vim 模式（可选）
```
src/vim/
├── 模态键位映射 (hjkl, dd, yy)
├── Insert/Normal/Visual 模式
└── 命令行模式 (/:search, :set)
```

#### 8.7 验收标准
- 长对话（2000+ 消息）流畅
- 费用追踪准确
- 构建产物可分发
- 错误恢复无感知

---

## 附录 A：关键数据类型速查

### 消息类型

```typescript
type Message =
  | UserMessage        // 用户输入
  | AssistantMessage   // 助手响应
  | SystemMessage      // 系统消息
  | ProgressMessage    // 工具进度
  | AttachmentMessage  // 附件（图片、命令队列、hook 结果）
```

### 工具结果类型

```typescript
type ToolResult<T> = {
  data: T;                    // 输出数据
  newMessages?: Message[];    // 注入额外消息
  contextModifier?: (ctx) => ctx;  // 修改上下文
};
```

### 权限结果类型

```typescript
type PermissionResult =
  | { behavior: 'allow'; updatedInput? }
  | { behavior: 'ask'; message; suggestions? }
  | { behavior: 'deny'; message; decisionReason };
```

### 流事件类型

```typescript
type StreamEvent =
  | { type: 'message_start' }
  | { type: 'content_block_start'; content_block }
  | { type: 'content_block_delta'; delta }
  | { type: 'content_block_stop' }
  | { type: 'message_delta'; delta; usage }
  | { type: 'message_stop' };
```

---

## 附录 B：复刻优先级矩阵

| 功能 | 用户价值 | 实现复杂度 | 推荐 Phase |
|------|---------|-----------|-----------|
| CLI 入口 + API 调用 | ⭐⭐⭐⭐⭐ | ⭐⭐ | Phase 1 |
| 流式输出 | ⭐⭐⭐⭐⭐ | ⭐⭐ | Phase 1 |
| Bash 工具 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Phase 2 |
| 文件读写工具 | ⭐⭐⭐⭐⭐ | ⭐⭐ | Phase 2 |
| Glob/Grep 工具 | ⭐⭐⭐⭐ | ⭐⭐ | Phase 2 |
| 交互式 REPL | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Phase 3 |
| 消息渲染 | ⭐⭐⭐⭐ | ⭐⭐⭐ | Phase 3 |
| 会话持久化 | ⭐⭐⭐⭐ | ⭐⭐⭐ | Phase 4 |
| 自动压缩 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Phase 4 |
| 权限系统 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Phase 5 |
| CLAUDE.md | ⭐⭐⭐⭐ | ⭐⭐⭐ | Phase 6 |
| Git 集成 | ⭐⭐⭐ | ⭐⭐ | Phase 6 |
| Hooks 系统 | ⭐⭐⭐ | ⭐⭐⭐⭐ | Phase 6 |
| Thinking 模式 | ⭐⭐⭐ | ⭐⭐ | Phase 6 |
| 多 Provider | ⭐⭐⭐ | ⭐⭐⭐ | Phase 6 |
| 子代理 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Phase 7 |
| MCP 集成 | ⭐⭐⭐ | ⭐⭐⭐⭐ | Phase 7 |
| Slash 命令 | ⭐⭐⭐ | ⭐⭐⭐ | Phase 7 |
| 虚拟滚动 | ⭐⭐ | ⭐⭐⭐⭐ | Phase 8 |
| 流式工具执行 | ⭐⭐⭐ | ⭐⭐⭐⭐ | Phase 8 |
| 遥测监控 | ⭐⭐ | ⭐⭐ | Phase 8 |
| IDE 桥接 | ⭐⭐ | ⭐⭐⭐⭐ | Phase 8 |
| Vim 模式 | ⭐ | ⭐⭐⭐ | Phase 8 |

---

## 附录 C：可删减模块

以下模块在原代码库中存在但对核心功能非必需：

| 模块 | 状态 | 说明 |
|------|------|------|
| Computer Use (@ant/*) | 已存根 | Anthropic 内部功能 |
| 音频/图片 NAPI | 已存根 | 语音/图片处理 |
| Analytics / GrowthBook | 已存根 | 分析/AB 测试 |
| Magic Docs | 已删除 | 文档生成 |
| Voice Mode | 已删除 | 语音输入 |
| LSP Server | 已删除 | 语言服务 |
| Plugins / Marketplace | 已删除 | 插件市场 |
| MCP OAuth | 已简化 | OAuth 认证 |
| Agent Swarms | 门控 | 团队/群集 |
| Proactive Mode | 门控 | 主动模式 |
| Bridge/IDE | 可选 | IDE 集成 |
| Vim Mode | 可选 | Vim 键位 |

---

> **文档版本**: v1.0
> **分析日期**: 2026-04-04
> **基于代码库版本**: claude-js v1.0.3
