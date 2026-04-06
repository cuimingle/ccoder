# Claude Code Python — Phase 4: TUI/REPL with Textual

## Context

Phases 1-3 complete: skeleton, 15 tools, permissions/hooks/compaction. Pipe mode (`-p`) works end-to-end. `main.py` prints "Interactive REPL not yet implemented" for non-pipe mode. Phase 4 adds the Textual TUI: streaming message display, user input with history, and interactive permission prompts.

**Key existing APIs:**
- `QueryEngine.run_turn(user_input, on_text, on_tool_use) -> QueryResult`
- `PermissionChecker` — MANUAL mode defaults to ALLOW (needs ASK_USER for TUI prompting)
- `textual>=0.80.0` already in `pyproject.toml`

---

## Architecture

```
ClaudeCodeApp (Textual App)
  ├── Header
  ├── Messages widget         # Scrollable conversation display
  │   ├── User messages       # Plain text
  │   ├── Assistant chunks    # Streaming text, updated in place
  │   ├── Tool calls/results  # Name + input summary, result content
  │   └── System messages     # Compact, errors, etc.
  ├── PermissionPrompt        # Inline prompt (hidden by default, shows for ASK_USER)
  ├── PromptInput             # Input with history, Enter to submit
  └── Footer / Status bar     # Model, tokens, CWD
```

**Streaming flow:**
1. User submits text → `PromptInput.Submitted` message
2. App runs `engine.run_turn(text, on_text, on_tool_use)` as Textual worker (`thread=False`)
3. `on_text(chunk)` → `Messages.append_assistant_chunk(chunk)` (updates last Static widget in-place)
4. `on_tool_use(name, input)` → `Messages.append_tool_call(name, input)`
5. Turn complete → finalize, re-enable input

**Permission flow (asyncio.Event-based):**
1. `ToolExecutor` calls `permission_callback(tool_name, tool_input)` when ASK_USER
2. Callback shows `PermissionPrompt`, creates `asyncio.Event`, awaits it
3. User clicks Allow/Deny → `PermissionPrompt.Resolved` message → sets Event
4. Callback returns result → executor continues or denies

Everything runs on Textual's event loop (worker with `thread=False`), so no thread-safety issues.

---

## File Map

### New files (7 source + 3 test)

| File | Task | Purpose |
|------|------|---------|
| `packages/app/state/__init__.py` | 21 | Package init |
| `packages/app/state/app_state.py` | 21 | AppState dataclass (UI-relevant state) |
| `packages/app/components/__init__.py` | 23 | Package init |
| `packages/app/components/messages.py` | 23 | Messages widget (streaming conversation display) |
| `packages/app/components/prompt_input.py` | 24 | Input widget with history |
| `packages/app/components/permission_prompt.py` | 25 | Permission dialog for manual mode |
| `packages/app/screens/__init__.py` | 26 | Package init |
| `packages/app/screens/repl.py` | 26 | ClaudeCodeApp — main Textual app |
| `tests/test_app_state.py` | 28 | AppState tests |
| `tests/test_repl.py` | 28 | REPL integration tests (Textual pilot) |
| `tests/test_components.py` | 28 | Component unit tests |

### Modified files

| File | Task | Changes |
|------|------|---------|
| `packages/app/types/permissions.py` | 22 | Add `ASK_USER` to PermissionResult enum |
| `packages/app/permissions.py` | 22 | MANUAL mode returns ASK_USER instead of ALLOW |
| `packages/app/tool_executor.py` | 22 | Add `permission_callback` param, handle ASK_USER |
| `packages/app/query_engine.py` | 22 | Pass `permission_callback` through to ToolExecutor |
| `packages/app/main.py` | 27 | Launch Textual app for REPL mode |

---

## Tasks

### Task 21: AppState (no deps)

**Files:** `packages/app/state/__init__.py`, `packages/app/state/app_state.py`

```python
@dataclass
class AppState:
    cwd: str
    model: str
    permission_mode: str = "manual"
    is_busy: bool = False
    input_history: list[str] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    turn_count: int = 0
```

Minimal — `QueryEngine` already tracks messages/tokens. AppState holds UI-relevant state only.

---

### Task 22: Permission ASK_USER flow (no deps)

**Modify:** `types/permissions.py`, `permissions.py`, `tool_executor.py`, `query_engine.py`

**22a.** Add `ASK_USER = "ask_user"` to `PermissionResult` enum.

**22b.** `PermissionChecker._check_manual_mode()`: no-match returns `ASK_USER` instead of `ALLOW`.

**22c.** `ToolExecutor.__init__` gains `permission_callback: Callable | None = None`:
```python
if decision.result == PermissionResult.ASK_USER:
    if self._permission_callback is None:
        pass  # No UI — treat as ALLOW (pipe mode backward compat)
    else:
        user_result = await self._permission_callback(tool.name, tool_input)
        if user_result in (PermissionResult.DENY, PermissionResult.DENY_ALWAYS):
            self.permission_checker.record_session_decision(...)
            return ToolResult(content="Permission denied by user.", is_error=True)
        if user_result == PermissionResult.ALLOW_ALWAYS:
            self.permission_checker.record_session_decision(...)
```

**22d.** `QueryEngine.__init__` accepts `permission_callback` and passes to `ToolExecutor`.

**Tests:** Existing tests must still pass (ASK_USER treated as ALLOW when no callback). Add test for callback flow.

---

### Task 23: Messages widget (no deps)

**File:** `packages/app/components/messages.py`

Textual `VerticalScroll` widget displaying conversation. Methods:
- `append_user(text)` — adds user message Static
- `append_assistant_chunk(text)` — updates last assistant Static in-place (streaming)
- `finalize_assistant()` — marks current assistant message as complete
- `append_tool_call(name, input)` — shows tool invocation info
- `append_tool_result(name, content, is_error)` — shows tool result (truncated if long)
- `append_system(text)` — system messages (compact notification, cancel, etc.)

Uses Rich markup for formatting: tool names bold, errors red, user messages with `>` prefix.

---

### Task 24: PromptInput widget (no deps)

**File:** `packages/app/components/prompt_input.py`

Extends Textual `Input`:
- Enter submits (posts `PromptInput.Submitted(text)`)
- Up/Down arrows navigate history (`AppState.input_history`)
- Ctrl+C posts `CancelRequested` message
- `disabled` when app is busy

---

### Task 25: PermissionPrompt widget (depends on Task 22)

**File:** `packages/app/components/permission_prompt.py`

Inline widget (hidden by default). When shown:
- Displays tool name + input summary
- Four buttons: Allow / Allow Always / Deny / Deny Always
- Posts `PermissionPrompt.Resolved(result)` on button click

---

### Task 26: REPLScreen — main Textual app (depends on Tasks 21-25)

**File:** `packages/app/screens/repl.py`

```python
class ClaudeCodeApp(App):
    CSS = """..."""
    BINDINGS = [("ctrl+d", "quit"), ("ctrl+l", "clear_screen")]
    
    def compose(self):
        yield Header(show_clock=False)
        yield Messages(id="messages")
        yield PermissionPrompt(id="permission")
        yield PromptInput(id="input")
        yield Footer()
```

**Key handlers:**
- `on_prompt_input_submitted` → run `_run_query()` as worker (thread=False)
- `_run_query(text)` → `engine.run_turn(text, on_text=..., on_tool_use=...)`
- `on_text` callback → `messages.append_assistant_chunk(chunk)`
- Turn complete → finalize, update status, re-enable input
- `_permission_callback` → show PermissionPrompt, await asyncio.Event, return result
- `on_prompt_input_cancel_requested` → cancel worker, append "Cancelled" system message

---

### Task 27: Wire main.py (depends on Task 26)

**Modify:** `packages/app/main.py`

Replace the "not yet implemented" branch:
```python
from app.screens.repl import ClaudeCodeApp
from app.state.app_state import AppState

state = AppState(cwd=cwd, model=model, permission_mode="manual")
engine = QueryEngine(cwd=cwd, api_key=api_key, base_url=api_base, model=model,
                     permission_mode="manual")
app = ClaudeCodeApp(engine=engine, state=state)
app.run()
```

---

### Task 28: Tests (depends on Tasks 21-27)

**Files:** `tests/test_app_state.py`, `tests/test_repl.py`, `tests/test_components.py`

Using Textual's `async with app.run_test() as pilot:` framework:
- AppState: dataclass construction, defaults
- PromptInput: type → Enter → Submitted message posted
- Messages: append_user/append_assistant_chunk → verify widget content
- PermissionPrompt: show → click Allow → Resolved message with ALLOW
- Integration: mock QueryEngine, type input, verify streaming display

---

## Task Dependency Graph

```
Task 21 (AppState)          ─┐
Task 22 (ASK_USER flow)     ─┤
Task 23 (Messages widget)   ─┼─> Task 26 (REPLScreen) ──> Task 27 (main.py) ──> Task 28 (Tests)
Task 24 (PromptInput)       ─┤
Task 25 (PermissionPrompt)  ─┘
```

Tasks 21-24 are independent → parallel. Task 25 depends on 22 (ASK_USER type). Task 26 needs all. Tasks 27-28 sequential after 26.

---

## Verification

1. **Unit tests:** `uv run pytest tests/test_app_state.py tests/test_components.py tests/test_repl.py -v`
2. **Full suite:** `uv run pytest -v` (no regressions, all 160+ existing tests pass)
3. **Pipe mode still works:** `echo "say hello" | uv run python -m app -p`
4. **REPL mode:** `uv run python -m app` launches TUI, type a message, see streaming response
5. **Permission prompt:** Set manual mode, trigger a tool call → permission dialog appears → Allow/Deny works
6. **Ctrl+C cancels:** While streaming, Ctrl+C interrupts and shows "Cancelled"
7. **Ctrl+D quits:** Exits the TUI cleanly
