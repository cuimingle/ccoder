# TUI Input Commands Implementation Plan

> Target: claude-code-python
> Reference: claude-code-run (TypeScript)
> Date: 2026-04-06

## Context

Python 版 claude-code-python 当前仅有 4 个斜杠命令和 2 个快捷键。TypeScript 参考实现有 70+ 命令、40+ 快捷键、bash 输入模式、可配置快捷键系统和 Skill 加载系统。本计划通过 8 个阶段弥合差距，按用户价值优先级排序。

**当前状态：** 4 个命令 (/clear, /compact, /cost, /help)，2 个快捷键 (Ctrl+D, Ctrl+L)，无 bash 模式，无 skill 系统。

---

## Phase 1: 输入模式系统 & Bash 模式 (`!command`) — 规模: S

### 目标
支持 `!git status` 直接执行 shell 命令。建立输入模式基础设施。

### 新建文件
| 文件 | 说明 |
|------|------|
| `app/input_modes.py` | `InputMode` 枚举 (PROMPT, BASH)，`detect_mode()`，`strip_mode_prefix()`，`prepend_mode_prefix()` |
| `app/commands/bash_exec.py` | `async execute_bash(command, cwd) -> CommandResult`，使用 `asyncio.create_subprocess_shell`（复用 `app/tools/bash_tool.py` 的模式） |
| `tests/test_input_modes.py` | 输入模式检测测试 |
| `tests/test_bash_exec.py` | Bash 执行测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `app/components/prompt_input.py` | `UserSubmitted` 消息添加 `mode: InputMode` 字段；添加 Shift+Tab 切换模式；按模式更新 placeholder |
| `app/screens/repl.py` | `on_prompt_input_user_submitted` 中检测模式；BASH 模式直接调用 `execute_bash()` |

### 实现要点
```python
# app/input_modes.py
class InputMode(Enum):
    PROMPT = "prompt"
    BASH = "bash"

def detect_mode(text: str) -> InputMode:
    return InputMode.BASH if text.strip().startswith("!") else InputMode.PROMPT

def strip_mode_prefix(text: str, mode: InputMode) -> str:
    if mode == InputMode.BASH:
        return text.strip().lstrip("!").strip()
    return text
```

---

## Phase 2: 基本斜杠命令 — 规模: M

### 目标
实现最高价值的缺失命令：/model, /diff, /export, /session, /resume, /rewind, /exit

### 新建文件
| 文件 | 命令 | 说明 |
|------|------|------|
| `app/commands/exit.py` | `/exit` | 退出应用（别名: `q`, `quit`），设置 `should_exit=True` |
| `app/commands/model.py` | `/model [name]` | 无参数显示当前模型，有参数切换模型 |
| `app/commands/diff.py` | `/diff [args]` | 在 cwd 中运行 `git diff` |
| `app/commands/export.py` | `/export` | 将对话序列化为 markdown 文件 |
| `app/commands/session.py` | `/session`, `/resume [id]` | 保存/加载会话到 `~/.claude/sessions/` |
| `app/commands/rewind.py` | `/rewind [n]` | 移除最后 N 对 user+assistant 消息 |
| `tests/test_commands_phase2.py` | | 所有新命令的测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `app/command_registry.py` | `CommandResult` 添加 `should_exit: bool = False` |
| `app/commands/__init__.py` | 导入并注册所有新命令 |
| `app/query_engine.py` | 添加 `model` 属性；传播 `should_exit` |

### 关键改进：引入 CommandContext 数据类
```python
@dataclass
class CommandContext:
    engine: QueryEngine
    registry: CommandRegistry
    total_input_tokens: int
    total_output_tokens: int
    turn_count: int
    cwd: str
    settings: Settings | None = None
    app_state: AppState | None = None
```
替代当前的 `dict[str, Any]`，提供类型安全。

---

## Phase 3: 可配置快捷键系统 — 规模: L

### 目标
用可配置系统替代硬编码的 BINDINGS，从 `~/.claude/keybindings.json` 加载。

### 新建文件
| 文件 | 说明 |
|------|------|
| `app/keybindings/__init__.py` | `KeybindingRegistry` 类：`get_action(key, context)`, `get_key(action)`, `get_bindings_for_context(context)` |
| `app/keybindings/types.py` | `KeyBinding` 数据类 (key, action, context, description)，`KeybindingAction` 枚举 |
| `app/keybindings/defaults.py` | `DEFAULT_BINDINGS` 列表（ctrl+d→quit, ctrl+l→clear, shift+tab→cycle_mode, ctrl+r→history_search 等） |
| `app/keybindings/loader.py` | `load_keybindings()` 加载 JSON，合并默认值，过滤保留快捷键 |
| `tests/test_keybindings.py` | 快捷键系统测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `app/screens/repl.py` | 用 `KeybindingRegistry` 动态生成绑定替换硬编码 `BINDINGS`；支持 `command:*` 动作类型（命令桥接） |
| `app/components/prompt_input.py` | 接受 `KeybindingRegistry` 参数；`_on_key` 中使用注册表 |

### 默认快捷键
```python
DEFAULT_BINDINGS = [
    KeyBinding(key="ctrl+d", action="quit", context="global"),
    KeyBinding(key="ctrl+l", action="clear_screen", context="global"),
    KeyBinding(key="shift+tab", action="cycle_mode", context="chat_input"),
    KeyBinding(key="ctrl+r", action="history_search", context="chat_input"),
    KeyBinding(key="ctrl+g", action="external_editor", context="chat_input"),
    KeyBinding(key="ctrl+s", action="stash_input", context="chat_input"),
    KeyBinding(key="ctrl+o", action="transcript", context="global"),
]

RESERVED_SHORTCUTS = {"ctrl+c", "ctrl+d", "ctrl+z", "ctrl+m"}
```

### 命令桥接模式
快捷键动作以 `command:` 为前缀时（如 `command:commit`），自动提交 `/commit` 作为输入：
```python
if action.startswith("command:"):
    command_name = action.split(":", 1)[1]
    # Submit /{command_name} as user input
```

---

## Phase 4: 命令自动补全 — 规模: M

### 目标
输入 `/` 时 Tab 补全斜杠命令。

### 新建文件
| 文件 | 说明 |
|------|------|
| `app/components/autocomplete.py` | `CommandAutoComplete`: `get_suggestions(prefix)`, `get_best_match(prefix)` |
| `app/components/autocomplete_overlay.py` | Textual 浮动列表组件；Up/Down 导航，Tab 接受，Escape 关闭 |
| `tests/test_autocomplete.py` | 自动补全测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `app/components/prompt_input.py` | 接受 `CommandRegistry`；输入以 `/` 开头时显示建议列表 |

---

## Phase 5: 历史搜索 (Ctrl+R) — 规模: M

### 目标
交互式反向历史搜索。

### 新建文件
| 文件 | 说明 |
|------|------|
| `app/components/history_search.py` | `HistorySearch(Container)` 组件；显示 `(reverse-i-search)'query':` 提示；Ctrl+R 循环匹配；Tab/Escape 接受；Enter 执行 |
| `tests/test_history_search.py` | 历史搜索测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `app/components/prompt_input.py` | Ctrl+R 挂载 `HistorySearch` 覆盖层；接受时填充输入 |

---

## Phase 6: 外部编辑器 & 多行输入 — 规模: M

### 目标
Ctrl+G 打开 $EDITOR 编辑复杂输入。

### 新建文件
| 文件 | 说明 |
|------|------|
| `app/components/external_editor.py` | `async open_external_editor(initial_text) -> str \| None`；使用 `app.suspend()` + subprocess；读取 $EDITOR（默认 vi） |
| `tests/test_external_editor.py` | 外部编辑器测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `app/screens/repl.py` | 添加外部编辑器快捷键处理；提交编辑器结果 |
| `app/components/prompt_input.py` | Shift+Enter 插入换行（如果 Input 组件支持） |

### 实现策略
```python
async def open_external_editor(initial_text: str = "") -> str | None:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(initial_text)
        tmp_path = f.name
    # app.suspend() pauses Textual TUI
    proc = await asyncio.create_subprocess_exec(editor, tmp_path)
    await proc.wait()
    result = Path(tmp_path).read_text()
    Path(tmp_path).unlink()
    return result if result.strip() else None
```

---

## Phase 7: Skill 系统 — 规模: XL

### 目标
从磁盘加载 Skills (.claude/skills/*/SKILL.md)，解析 frontmatter，注册为命令。

### 新建文件
| 文件 | 说明 |
|------|------|
| `app/skills/__init__.py` | 包初始化 |
| `app/skills/types.py` | `SkillConfig` 数据类（17 字段：name, description, when_to_use, allowed_tools, model, effort, context 等） |
| `app/skills/parser.py` | `parse_skill_md(path) -> SkillConfig \| None`；提取 YAML frontmatter，解析字段，存储 body 为 prompt_template |
| `app/skills/loader.py` | `load_skills(cwd) -> list[SkillConfig]`；扫描 `{cwd}/.claude/skills/` 和 `~/.claude/skills/`；按名称去重（项目优先于用户） |
| `app/skills/variables.py` | `substitute_variables(template, args, skill_dir, session_id) -> str`；替换 $ARGUMENTS, ${CLAUDE_SKILL_DIR}, ${CLAUDE_SESSION_ID} |
| `app/skills/executor.py` | `SkillExecutor`: `execute_inline()` 替换变量并返回 prompt，`execute_fork()` 创建子 QueryEngine |
| `tests/test_skills.py` | Skill 系统完整测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `app/commands/__init__.py` | 内置命令注册后调用 `load_skills(cwd)`，将 user_invocable skills 注册为 PromptCommand (inline) 或 LocalCommand (fork) |
| `app/tools/skill_tool.py` | 接受 registry 引用以动态查找 skills |

### 依赖
`pyproject.toml` 添加 `pyyaml`（或使用轻量正则 frontmatter 解析器）

### Skill 执行模式
- **inline**（默认）：替换变量后将 prompt 注入主对话
- **fork**（`context: fork`）：创建独立子 QueryEngine，使用 skill 指定的 allowed_tools 和 model

---

## Phase 8: 扩展命令 — 规模: L

### 目标
补充剩余实用命令：配置、信息、账户、环境。

### 新建文件
| 文件 | 命令 | 说明 |
|------|------|------|
| `app/commands/config_commands.py` | `/permissions`, `/hooks`, `/config` | 显示权限规则、hooks、合并设置 |
| `app/commands/info_commands.py` | `/stats`, `/status`, `/doctor`, `/usage` | 扩展统计、系统状态、诊断、API 使用 |
| `app/commands/account_commands.py` | `/login`, `/logout` | 存储/清除 API key |
| `app/commands/env_commands.py` | `/add-dir`, `/context`, `/files` | 添加工作目录、显示上下文、列出引用文件 |
| `tests/test_commands_phase3.py` | | 所有新命令测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `app/commands/__init__.py` | 导入并注册所有新命令 |

---

## 阶段总览

| 阶段 | 名称 | 规模 | 新建文件 | 修改文件 | 依赖 |
|------|------|------|---------|---------|------|
| 1 | 输入模式 + Bash | S | 4 | 2 | 无 |
| 2 | 基本命令 | M | 8 | 3 | Phase 1 |
| 3 | 快捷键系统 | L | 5 | 2 | Phase 1 |
| 4 | 自动补全 | M | 3 | 1 | Phase 2 |
| 5 | 历史搜索 | M | 2 | 1 | Phase 3 |
| 6 | 外部编辑器 | M | 2 | 2 | Phase 3 |
| 7 | Skill 系统 | XL | 7 | 2 | Phase 2+3 |
| 8 | 扩展命令 | L | 5 | 1 | Phase 2 |

### 依赖图
```
Phase 1 (Input Modes)
  ├── Phase 2 (Essential Commands) ──→ Phase 8 (Extended Commands)
  │                                  └── Phase 4 (Autocomplete)
  └── Phase 3 (Keybindings) ──→ Phase 5 (History Search)
                              └── Phase 6 (External Editor)
                              
Phase 2 + Phase 3 ──→ Phase 7 (Skill System)
```

---

## 验证策略

每个阶段完成后：
1. `uv run pytest tests/` — 所有现有 + 新测试通过
2. `uv run ccoder` — 启动 TUI，手动测试新功能
3. 具体验证项：
   - **Phase 1:** 输入 `!echo hello` 验证输出；Shift+Tab 切换模式
   - **Phase 2:** `/help` 显示所有新命令；`/model` 显示/切换模型；`/diff` 显示 git diff
   - **Phase 3:** 修改 `~/.claude/keybindings.json` 后重启验证生效
   - **Phase 4:** 输入 `/he` 后按 Tab 补全为 `/help`
   - **Phase 5:** Ctrl+R 打开搜索，输入关键词匹配历史
   - **Phase 6:** Ctrl+G 打开编辑器，编辑后内容提交
   - **Phase 7:** 创建 `.claude/skills/test/SKILL.md`，通过 `/test` 调用
   - **Phase 8:** `/doctor` 运行诊断；`/permissions` 显示规则

---

## 关键文件参考

| 文件 | 角色 | 涉及阶段 |
|------|------|---------|
| `app/components/prompt_input.py` | 输入组件核心 | 1, 3, 4, 5 |
| `app/command_registry.py` | 命令注册基础设施 | 2 |
| `app/screens/repl.py` | TUI 主界面 | 1, 3, 6 |
| `app/commands/__init__.py` | 命令注册中心 | 2, 7, 8 |
| `app/query_engine.py` | 查询引擎 | 2, 7 |
| `app/tools/bash_tool.py` | Bash 工具（复用模式） | 1 |
| `app/settings.py` | 设置加载 | 3, 8 |
