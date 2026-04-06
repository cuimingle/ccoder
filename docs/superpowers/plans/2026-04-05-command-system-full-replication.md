# Phase: Command System Full Replication

> **Goal:** 完整复刻 TypeScript 参考实现的 command 系统到 Python 实现，修复现有 bug，补齐缺失功能。

## 1. 现状差距分析

### 1.1 命令类型体系

| 特性 | TS 参考 | Python 当前 | 差距 |
|------|---------|------------|------|
| LocalCommand | ✅ 返回 `{type:'text', value}` / `{type:'compact'}` / `{type:'skip'}` | ⚠️ 只有 `CommandResult(text=...)` | 缺少 compact/skip result type |
| LocalJSXCommand | ✅ 返回 React/Ink 组件 | ❌ 不存在 | 需要 Textual Widget 等价物 |
| PromptCommand | ✅ `getPromptForCommand()` + `allowedTools` + `context` (inline/fork) | ⚠️ 只有 `get_prompt()` | 缺少 allowedTools, context 模式 |
| CommandBase 字段 | `argumentHint`, `isEnabled`, `isHidden`, `supportsNonInteractive`, `immediate`, `isSensitive`, `aliases`, `availability` | 只有 `name`, `description`, `aliases`, `is_hidden` | 缺失大量元数据字段 |

### 1.2 已实现命令

| 命令 | TS 行为 | Python 当前 | 问题 |
|------|---------|------------|------|
| `/clear` | 执行 SessionEnd hooks → 清理 tasks → 清空 messages → 重置 cwd → regenerate session ID → 执行 SessionStart hooks | 直接在 QueryEngine 里 hardcode `self.clear()` 只清空 messages/counters | 1. 没有走 registry 2. 没有 hook 支持 3. 不够完整 |
| `/compact` | 支持自定义指令 → micro-compact → reactive/traditional compaction → pre/post-compact hooks | 直接在 QueryEngine 里 hardcode，调用 compaction 模块 | 1. 没有走 registry 2. 不支持自定义参数 |
| `/cost` | 区分订阅用户/API用户 → 显示 per-model usage/duration/cache/lines changed | 硬编码 Opus 价格，只显示 input/output tokens | 缺少 per-model tracking, duration, cache tokens, lines changed |
| `/help` | LocalJSXCommand 渲染交互式 UI | LocalCommand 返回文本列表 | 功能够用但偏简陋 |

### 1.3 命令调度

| 特性 | TS 参考 | Python 当前 |
|------|---------|------------|
| 调度入口 | `processSlashCommand.tsx` — 统一路由 | `QueryEngine.run_turn()` 里 inline if/elif |
| clear/compact | 通过 registry 正常调度 | 在 registry 之前 hardcode 特殊处理 |
| PromptCommand 执行 | 展开为 message → 发送给模型 → 模型带 allowedTools 执行 | 返回 `should_query=True` + `prompt_content`，但 QueryEngine 没有处理 |
| 未知命令 | 返回错误 + 建议相似命令 | 返回 "Unknown command" |

### 1.4 Cost Tracking

| 特性 | TS 参考 | Python 当前 |
|------|---------|------------|
| Per-model usage | ✅ 按 model 分别记录 input/output/cache/web search | ❌ 只有全局 total |
| Duration tracking | ✅ API duration + wall duration + tool duration | ❌ 无 |
| Cache tokens | ✅ cache_read + cache_creation 分别跟踪 | ❌ 无 |
| Lines changed | ✅ added/removed 行数 | ❌ 无 |
| 动态定价 | ✅ `calculateUSDCost(model, usage)` | ❌ 硬编码 Opus 价格 |
| 格式化输出 | cost + duration + lines + per-model breakdown | 仅 turns + tokens + cost |

---

## 2. 实施计划

### Step 1: 增强 Command 类型系统

**文件:** `packages/app/command_registry.py`

**改动:**

```python
@dataclass
class CommandResult:
    """Result of a slash command execution."""
    type: str = "text"           # "text" | "compact" | "skip"
    text: str = ""
    should_query: bool = False
    prompt_content: str = ""
    # For compact type
    compaction_result: Any = None

@dataclass
class CommandBase:
    """Shared fields for all command types."""
    name: str
    description: str
    aliases: list[str] = field(default_factory=list)
    argument_hint: str = ""       # 显示参数格式 e.g. "[model]"
    is_hidden: bool = False
    is_enabled: Callable[[], bool] | None = None  # Feature flag
    supports_non_interactive: bool = False

@dataclass
class LocalCommand(CommandBase):
    handler: Callable[[str, CommandContext], Awaitable[CommandResult]]
    type: str = field(default="local", init=False)

@dataclass
class PromptCommand(CommandBase):
    get_prompt: Callable[[str, CommandContext], Awaitable[list[dict]]]
    progress_message: str = ""
    allowed_tools: list[str] = field(default_factory=list)  # e.g. ["Bash(git add:*)"]
    content_length: int = 0
    type: str = field(default="prompt", init=False)
```

新增 `CommandContext` 替代裸 `dict`:
```python
@dataclass
class CommandContext:
    engine: Any  # QueryEngine (forward ref)
    registry: CommandRegistry
    cwd: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    turn_count: int = 0
    messages: list[Message] = field(default_factory=list)
    tools: list[Tool] = field(default_factory=list)
    model: str = ""
```

### Step 2: 增强 Cost Tracking

**新文件:** `packages/app/cost_tracker.py`

从 TS `cost-tracker.ts` 复刻核心逻辑：

```python
@dataclass
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float = 0.0

@dataclass
class CostState:
    total_cost_usd: float = 0.0
    total_api_duration: float = 0.0      # seconds
    total_wall_duration: float = 0.0
    total_lines_added: int = 0
    total_lines_removed: int = 0
    model_usage: dict[str, ModelUsage] = field(default_factory=dict)
    session_start_time: float = 0.0

class CostTracker:
    def __init__(self):
        self._state = CostState(session_start_time=time.time())
    
    def add_usage(self, model: str, usage: Usage, api_duration: float):
        """Record API usage for a model."""
        cost = calculate_cost(model, usage)
        ...
    
    def add_lines_changed(self, added: int, removed: int): ...
    
    def format_total_cost(self) -> str:
        """Format cost display matching TS formatTotalCost()."""
        ...
    
    def format_model_usage(self) -> str:
        """Per-model breakdown."""
        ...
```

**定价表** (`packages/app/utils/model_cost.py`):
```python
MODEL_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-haiku-4-5": {"input": 0.8, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
}

def calculate_cost(model: str, usage) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["claude-opus-4-6"])
    cost = (
        usage.input_tokens * pricing["input"] / 1_000_000
        + usage.output_tokens * pricing["output"] / 1_000_000
        + usage.cache_read_input_tokens * pricing["cache_read"] / 1_000_000
        + usage.cache_creation_input_tokens * pricing["cache_write"] / 1_000_000
    )
    return cost
```

### Step 3: 重写 /cost 命令

**文件:** `packages/app/commands/cost.py`

对齐 TS `formatTotalCost()` 输出格式:

```
Total cost:            $0.1234
Total duration (API):  2m 34s
Total duration (wall): 5m 12s
Total code changes:    42 lines added, 15 lines removed
Usage by model:
          claude-opus-4-6:  12,345 input, 6,789 output, 1,234 cache read, 567 cache write ($0.0987)
        claude-sonnet-4-6:  3,456 input, 1,234 output, 0 cache read, 0 cache write ($0.0123)
```

### Step 4: 修复 /clear 和 /compact 调度

**问题:** `QueryEngine.run_turn()` 里 clear/compact 绕过了 registry：

```python
# 当前代码 (query_engine.py:71-77)
if command_name == "compact":
    return await self._handle_compact()
if command_name == "clear":
    self.clear()
    return QueryResult(response_text="Session cleared.", tool_calls=[])
```

**改法:** 将所有命令统一走 registry，command handler 里接收 engine 引用来执行实际操作：

```python
# clear handler
async def clear_handler(args: str, ctx: CommandContext) -> CommandResult:
    ctx.engine.clear()
    return CommandResult(text="Conversation cleared and context reset.")

# compact handler  
async def compact_handler(args: str, ctx: CommandContext) -> CommandResult:
    custom_instructions = args.strip() or None
    summary = await ctx.engine.compact(custom_instructions=custom_instructions)
    return CommandResult(type="compact", text=f"Conversation compacted.\n\n{summary}")
```

QueryEngine 里变为:
```python
cmd = parse_command(user_input)
if cmd is not None:
    command_name, args = cmd
    context = CommandContext(engine=self, registry=self._command_registry, ...)
    result = await self._command_registry.execute(command_name, args, context)
    
    if result.should_query:
        # PromptCommand: inject prompt as user message and run query
        self.messages.append(UserMessage(content=result.prompt_content))
        return await self._run_query(on_text, on_tool_use)
    
    return QueryResult(response_text=result.text, tool_calls=[])
```

### Step 5: 增强 /compact 支持自定义指令

**文件:** `packages/app/commands/compact.py` (新文件)

```python
async def compact_handler(args: str, ctx: CommandContext) -> CommandResult:
    custom_instructions = args.strip() if args.strip() else None
    summary = await ctx.engine.compact(custom_instructions=custom_instructions)
    return CommandResult(type="compact", text=f"Conversation compacted.\n\n{summary}")
```

同时更新 `compaction.py` 的 `compact_conversation()` 接受 `custom_instructions` 参数。

### Step 6: 增强 /help 命令

**文件:** `packages/app/commands/help.py`

对齐 TS 显示格式，增加 `argument_hint` 显示：

```
Available commands:
  /clear              Clear conversation history and free up context
  /compact [text]     Compact conversation context
  /cost               Show token usage and cost
  /help               Show available commands (aliases: /h, /?)
```

### Step 7: 集成 CostTracker 到 QueryEngine

**文件:** `packages/app/query_engine.py`

- 将 `total_input_tokens` / `total_output_tokens` 替换为 `CostTracker` 实例
- 在 query 返回后调用 `cost_tracker.add_usage(model, usage, api_duration)`
- `/cost` handler 从 `ctx.engine.cost_tracker` 读取数据

### Step 8: 增加缺失的简单命令

| 命令 | 类型 | 功能 |
|------|------|------|
| `/version` | local | 显示版本号 (从 pyproject.toml 读取) |

其他 TS 命令 (/model, /status, /diff, /config 等) 是 `local-jsx` 类型需要 Ink/React UI，超出本 phase 范围，留到 TUI 增强阶段。

---

## 3. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `packages/app/command_registry.py` | 修改 | 增强 CommandResult, 新增 CommandContext, 增强 CommandBase 字段 |
| `packages/app/cost_tracker.py` | **新建** | CostTracker + CostState + ModelUsage |
| `packages/app/utils/model_cost.py` | **新建** | 定价表 + calculate_cost() |
| `packages/app/commands/__init__.py` | 修改 | 更新 registry builder，使用 CommandContext |
| `packages/app/commands/cost.py` | 重写 | 使用 CostTracker，对齐 TS 输出格式 |
| `packages/app/commands/help.py` | 修改 | 显示 argument_hint，改进格式 |
| `packages/app/commands/compact.py` | **新建** | 独立 compact handler，支持自定义指令 |
| `packages/app/commands/clear.py` | **新建** | 独立 clear handler |
| `packages/app/commands/version.py` | **新建** | /version 命令 |
| `packages/app/query_engine.py` | 修改 | 集成 CostTracker, 统一命令调度, 处理 PromptCommand |
| `packages/app/query.py` | 修改 | 返回 api_duration, cache tokens |
| `packages/app/compaction.py` | 修改 | 接受 custom_instructions 参数 |
| `packages/app/services/api/claude.py` | 修改 | StreamEvent 里传递 cache token 信息 |

---

## 4. 实施顺序

```
Step 1: 增强类型系统 (command_registry.py)
    ↓
Step 2: CostTracker + 定价 (cost_tracker.py, utils/model_cost.py)
    ↓
Step 3: 重写 /cost (commands/cost.py)
    ↓
Step 4: 统一调度 — 修 clear/compact 绕过 registry 的 bug (query_engine.py, commands/clear.py, commands/compact.py)
    ↓
Step 5: 增强 /compact 支持自定义指令 (compaction.py)
    ↓
Step 6: 增强 /help (commands/help.py)
    ↓
Step 7: 集成 CostTracker (query_engine.py, query.py, claude.py)
    ↓
Step 8: 补 /version 等简单命令
```

## 5. 验证计划

- [ ] `uv run pytest tests/` — 全量测试通过
- [ ] `/cost` — 显示 per-model breakdown, duration, cache tokens, lines changed
- [ ] `/clear` — 走 registry 调度，清空 messages + counters + cost tracker
- [ ] `/compact` — 走 registry 调度，支持 `/compact 保留所有代码变更细节`
- [ ] `/compact` (无参数) — 默认行为不变
- [ ] `/help` — 显示所有命令含 argument_hint
- [ ] `/version` — 显示正确版本号
- [ ] `/unknown` — 返回 "Unknown command" 提示
- [ ] PromptCommand 流程: prompt_content 被注入为 user message 并触发 query
- [ ] pipe mode: 命令在非交互模式下也能工作 (supports_non_interactive)
