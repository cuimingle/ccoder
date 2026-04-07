# Claude Code TUI Input Commands Analysis

> Source: Analysis of [claude-code-run](../../../claude-code-run/) TypeScript implementation
> Target: [claude-code-python](../) Python implementation
> Date: 2026-04-06

---

## 1. Slash Commands — 70+ Built-in Commands

### Source Location

- **Command Registry:** `src/commands.ts:258-346`
- **Command Parsing:** `src/utils/slashCommandParsing.ts`
- **Command Execution:** `src/utils/processUserInput/processSlashCommand.tsx:309-525`
- **Type Definition:** `src/types/command.ts`

### Command Types

| Type | Description |
|------|-------------|
| `prompt` | Executed through Claude as a Skill |
| `local` | Executed locally with immediate results |
| `local-jsx` | Renders React/Ink UI components |

### Complete Command List

| Category | Commands |
|----------|----------|
| **Session** | `/clear`, `/compact`, `/cost`, `/exit`, `/resume`, `/session`, `/rewind` |
| **Model** | `/model`, `/effort`, `/fast`, `/passes` |
| **Code** | `/diff`, `/copy`, `/export`, `/branch` |
| **Permissions** | `/permissions`, `/plan`, `/sandbox` |
| **Config** | `/config`, `/hooks`, `/keybindings`, `/color`, `/theme`, `/vim`, `/output-style` |
| **Extensions** | `/mcp`, `/skills`, `/agents`, `/tasks`, `/reload-plugins` |
| **Account** | `/login`, `/logout`, `/install-github-app`, `/install-slack-app` |
| **Info** | `/help`, `/doctor`, `/stats`, `/status`, `/usage`, `/extra-usage`, `/rate-limit-options`, `/release-notes` |
| **Advanced** | `/memory`, `/tag`, `/rename`, `/stickers`, `/thinkback`, `/thinkback-play` |
| **Environment** | `/add-dir`, `/context`, `/files`, `/desktop`, `/ide`, `/mobile`, `/terminal-setup`, `/web-setup`, `/remote-env` |
| **Other** | `/btw`, `/chrome`, `/feedback`, `/heapdump`, `/privacy-settings`, `/upgrade`, `/voice`, `/pr-comments` |

### MCP Tool Commands

Format: `/mcp:tool-name (MCP) args`

---

## 2. Keyboard Shortcuts

### Source Location

- **Default Bindings:** `src/keybindings/defaultBindings.ts:32-340+`
- **Schema:** `src/keybindings/schema.ts`
- **Reserved:** `src/keybindings/reservedShortcuts.ts`
- **Loader:** `src/keybindings/loadUserBindings.ts`
- **Command Bridge:** `src/hooks/useCommandKeybindings.tsx`
- **User Config:** `~/.claude/keybindings.json`

### Global Context

| Shortcut | Action | Rebindable |
|----------|--------|------------|
| `Ctrl+C` | Interrupt (double-press to exit) | No |
| `Ctrl+D` | Exit | No |
| `Ctrl+L` | Redraw screen | Yes |
| `Ctrl+T` | Toggle TODO panel | Yes |
| `Ctrl+O` | Toggle Transcript view | Yes |
| `Ctrl+R` | History search | Yes |
| `Ctrl+Shift+B` | Toggle Brief/KAIROS mode | Yes |
| `Ctrl+Shift+F` / `Cmd+Shift+F` | Global search | Yes |
| `Ctrl+Shift+P` / `Cmd+Shift+P` | Quick open | Yes |
| `Meta+J` | Toggle terminal panel | Yes |
| `Ctrl+Shift+O` | Toggle teammate preview | Yes |

### Chat Input Context

| Shortcut | Action |
|----------|--------|
| `Enter` | Submit message |
| `Escape` | Cancel |
| `Shift+Tab` | Cycle input mode |
| `Meta+P` | Model picker |
| `Meta+O` | Fast mode toggle |
| `Meta+T` | Thinking mode toggle |
| `Up` / `Down` | History navigation |
| `Ctrl+G` / `Ctrl+X Ctrl+E` | External editor |
| `Ctrl+S` | Stash input |
| `Ctrl+V` | Paste image |
| `Ctrl+_` / `Ctrl+Shift+-` | Undo |
| `Ctrl+X Ctrl+K` | Kill all agents |
| `Shift+Up` | Message actions |
| `Space` | Push-to-talk (voice mode) |

### Autocomplete Context

| Shortcut | Action |
|----------|--------|
| `Tab` | Accept suggestion |
| `Escape` | Dismiss |
| `Up` / `Down` | Navigate suggestions |

### Confirmation Dialog

| Shortcut | Action |
|----------|--------|
| `Y` / `Enter` | Confirm |
| `N` / `Escape` | Reject |
| `Up` / `Down` | Navigate options |
| `Tab` | Next field |
| `Space` | Toggle option |
| `Shift+Tab` | Cycle mode |
| `Ctrl+E` | Toggle explanation |
| `Ctrl+D` | Toggle debug |

### Transcript View

| Shortcut | Action |
|----------|--------|
| `Ctrl+E` | Toggle show all |
| `Q` / `Escape` / `Ctrl+C` | Exit |

### History Search

| Shortcut | Action |
|----------|--------|
| `Ctrl+R` | Next match |
| `Tab` / `Escape` | Accept |
| `Ctrl+C` | Cancel |
| `Enter` | Execute |

### Platform Reserved (Not Rebindable)

- **macOS:** `Cmd+C`, `Cmd+V`, `Cmd+X`, `Cmd+Q`, `Cmd+W`, `Cmd+Tab`, `Cmd+Space`
- **Terminal:** `Ctrl+Z` (SIGTSTP), `Ctrl+\` (SIGQUIT), `Ctrl+M` (≡ Enter)

---

## 3. Special Input Prefixes & Modes

### Source Location

- **Input Modes:** `src/components/PromptInput/inputModes.ts:4-33`
- **Type Definitions:** `src/types/textInputTypes.ts:265-273`

### Input Modes

| Prefix | Mode | Description |
|--------|------|-------------|
| `!` | `bash` | Execute shell command directly (e.g. `!git status`) |
| `/` | slash command | Invoke built-in command or Skill |
| (none) | `prompt` | Normal conversation with Claude |

### All Mode Types

| Mode | Purpose |
|------|---------|
| `prompt` | Normal Claude conversation |
| `bash` | Shell command execution (starts with `!`) |
| `orphaned-permission` | Permission request handling |
| `task-notification` | Task system notifications |

### Functions

- `prependModeCharacterToInput()` — Add `!` prefix for bash mode
- `getModeFromInput()` — Detect mode from input string
- `getValueFromInput()` — Extract value without mode character

---

## 4. Skill System (Extensible Commands)

### Source Location

- **Bundled Skills:** `src/skills/bundledSkills.ts`
- **Skill Loader:** `src/skills/loadSkillsDir.ts`
- **Skill Tool:** SkillTool implementation
- **Docs:** `docs/extensibility/skills.mdx`

### Skill Loading Hierarchy

1. `.claude/skills/` — Project-level
2. `~/.claude/skills/` — User global
3. `$MANAGED_DIR/.claude/skills/` — Enterprise policy
4. Bundled skills (compiled in)
5. Plugin-loaded skills (dynamic)

### Skill File Format

Directory-based: `skill-name/SKILL.md`

### Frontmatter Fields (17 total)

```yaml
name: code-review                      # Display name
description: System code review        # Description
when_to_use: "code review, find bugs"  # AI auto-match hint
allowed-tools:                         # Tool whitelist
  - Read
  - Grep
argument-hint: "<file-or-directory>"   # CLI hint
arguments: [path]                      # Positional args → $ARGUMENTS
model: opus                            # Model override
effort: high                           # Effort level
context: fork | inline                 # Execution mode (default: inline)
agent: code-reviewer                   # Agent definition reference
user-invocable: true                   # Accessible via slash command
disable-model-invocation: false        # AI can auto-invoke
version: "1.0"                         # Version
paths:                                 # Conditional activation patterns
  - "src/**/*.ts"
hooks:                                 # Hook configuration
  PreToolUse:
    - command: ["echo", "checking"]
shell: ["bash"]                        # Shell environment
```

### Execution Modes

| Mode | Description |
|------|-------------|
| **inline** (default) | Prompt injected into main conversation, inherits parent context |
| **fork** (`context: fork`) | Runs in isolated sub-Agent with independent token budget |

### Variable Substitution

- `$ARGUMENTS` — Positional arguments from command invocation
- `${CLAUDE_SKILL_DIR}` — Skill directory path
- `${CLAUDE_SESSION_ID}` — Current session ID

---

## 5. Permission Modes

### Modes

| Mode | Trigger | Effect |
|------|---------|--------|
| `default` | Default state | Most operations require confirmation |
| `plan` | `/plan` or AI auto-trigger | Read-only tools only |
| `auto` | Settings config | Rules-based auto-approval |
| `bypass` | `--dangerously-skip-permissions` | All tools allowed |

### Five-Layer Permission Rule Hierarchy (highest → lowest priority)

1. `session` — "Always allow" during conversation
2. `cliArg` — `--allow` / `--deny` flags
3. `command` — Skill's `allowedTools` whitelist
4. `projectSettings` — `.claude/settings.json`
5. `userSettings` — `~/.claude/settings.json`
6. `policySettings` — Enterprise policy (overrides user)

---

## 6. CLI Flags Affecting TUI

| Flag | Effect |
|------|--------|
| `-p` / `--pipe` | Pipe mode, non-interactive |
| `--resume` | Restore previous session |
| `--allow <rule>` | Pre-approve permission rules |
| `--deny <rule>` | Pre-deny permission rules |
| `--add-dir` | Add extra working directory |
| `-c` / `--cwd` | Set working directory |
| `--dangerously-skip-permissions` | Bypass all permission checks |

---

## 7. Hook System — 22+ Events

### Hook Events

| Category | Events |
|----------|--------|
| **Session** | `SessionStart`, `SessionEnd`, `Setup` |
| **User** | `UserPromptSubmit`, `Stop`, `StopFailure` |
| **Tools** | `PreToolUse`, `PostToolUse`, `PostToolUseFailure` |
| **Permission** | `PermissionRequest`, `PermissionDenied` |
| **SubAgent** | `SubagentStart`, `SubagentStop` |
| **Compression** | `PreCompact`, `PostCompact` |
| **Collaboration** | `TeammateIdle`, `TaskCreated`, `TaskCompleted` |
| **MCP** | `Elicitation`, `ElicitationResult` |
| **Environment** | `ConfigChange`, `CwdChanged`, `FileChanged`, `InstructionsLoaded`, `WorktreeCreate`, `WorktreeRemove` |

### Hook Types

| Type | Description |
|------|-------------|
| `command` | Shell command execution |
| `prompt` | Inject into AI context |
| `agent` | Spawn sub-Agent |
| `http` | HTTP webhook |
| `callback` | Internal function |
| `function` | Runtime-registered |

### Configuration Example

```json
{
  "hooks": [{
    "event": "PreToolUse",
    "command": "check-permissions.sh",
    "shell": "bash",
    "if": "Bash(git push*)",
    "timeout": 10
  }]
}
```

---

## 8. Command Registration & Handling Mechanism

### Architecture

- **Master Registry:** `src/commands.ts` — Imports all commands, builds dynamic lists
- **Lookup:** `getCommand(commandName, commands)` — Retrieves command definition
- **Validation:** `hasCommand(commandName, commands)` — Checks existence
- **All Names:** `builtInCommandNames()` → `Set<string>`

### Processing Flow

```
User Input
    ↓
slashCommandParsing.ts: parse "/command args"
    ↓
processSlashCommand.tsx: route by command type
    ├─ prompt → Run through Claude as skill
    ├─ local → Execute locally, return result
    └─ local-jsx → Render React component
```

### Keybinding → Command Bridge

- Keybindings with `command:*` actions (e.g., `command:commit`)
- Detected by `useCommandKeybindings.tsx:37-107`
- Pressing keybinding submits `/<command-name>` as input
- Treated as user-invoked slash command

---

## 9. Current Python Implementation Status

### Already Implemented

| Component | Status | Location |
|-----------|--------|----------|
| Textual TUI | ✅ Full | `app/screens/repl.py` |
| PromptInput widget | ✅ Basic | `app/components/prompt_input.py` |
| Messages widget | ✅ Full | `app/components/messages.py` |
| PermissionPrompt | ✅ Full | `app/components/permission_prompt.py` |
| CommandRegistry | ✅ Infrastructure | `app/command_registry.py` |
| `/clear` | ✅ | `app/commands/__init__.py` |
| `/compact` | ✅ | `app/commands/__init__.py` |
| `/cost` | ✅ | `app/commands/cost.py` |
| `/help` | ✅ | `app/commands/help.py` |
| 27 Tools | ✅ | `app/tools/` |
| Settings system | ✅ | `app/settings.py` |
| Permission system | ✅ | `app/permissions.py` |
| Hook system | ✅ | `app/hooks.py` |
| Query engine | ✅ | `app/query_engine.py` |
| Keybindings (hardcoded) | ⚠️ Only 2 | `repl.py` (Ctrl+D, Ctrl+L) |

### Not Implemented (Gap Analysis)

| Feature | Priority | Complexity |
|---------|----------|------------|
| `!` bash input mode | High | Low |
| 60+ additional slash commands | High | Medium |
| Configurable keybindings system | Medium | High |
| Command autocomplete | Medium | Medium |
| Input mode cycling (Shift+Tab) | Medium | Low |
| External editor support (Ctrl+G) | Medium | Medium |
| History search (Ctrl+R) | Medium | Medium |
| Image paste support | Low | High |
| Skill loading from disk | High | High |
| Skill frontmatter parsing | High | Medium |
| Command→Keybinding bridge | Low | Medium |
| Multi-line input | Medium | Medium |
| Input stash (Ctrl+S) | Low | Low |
| Transcript view | Low | High |
| Quick open / Command palette | Low | High |
| Voice mode | Low | Very High |

---

## 10. Key Source Files Reference

### TypeScript Source (claude-code-run)

| File | Purpose |
|------|---------|
| `src/commands.ts` | Central command registry (70+ commands) |
| `src/utils/slashCommandParsing.ts` | Parse `/command args` format |
| `src/utils/processUserInput/processSlashCommand.tsx` | Execute slash commands |
| `src/keybindings/defaultBindings.ts` | Default keyboard shortcuts |
| `src/keybindings/reservedShortcuts.ts` | Non-rebindable shortcuts |
| `src/keybindings/loadUserBindings.ts` | User keybinding loader |
| `src/components/PromptInput/inputModes.ts` | Input mode (`!`) handling |
| `src/components/PromptInput/PromptInput.tsx` | Main input component |
| `src/hooks/useCommandKeybindings.tsx` | Command keybinding handler |
| `src/types/textInputTypes.ts` | Input mode type definitions |
| `src/skills/bundledSkills.ts` | Bundled skill loader |
| `src/skills/loadSkillsDir.ts` | Skill directory loader |

### Python Target (claude-code-python)

| File | Purpose |
|------|---------|
| `app/screens/repl.py` | Main TUI app (Textual) |
| `app/components/prompt_input.py` | Input widget |
| `app/components/messages.py` | Message display |
| `app/components/permission_prompt.py` | Permission dialog |
| `app/command_registry.py` | Command registry infrastructure |
| `app/commands/__init__.py` | Command parsing & built-ins |
| `app/commands/cost.py` | Cost command |
| `app/commands/help.py` | Help command |
| `app/query_engine.py` | Session orchestrator |
| `app/tool.py` | Tool Protocol definition |
| `app/tool_registry.py` | Tool registry |
| `app/tools/` | 27 tool implementations |
| `app/settings.py` | Settings loader |
| `app/permissions.py` | Permission checking |
| `app/hooks.py` | Hook execution |
