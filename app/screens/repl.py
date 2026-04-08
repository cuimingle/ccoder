"""ClaudeCodeApp — main Textual REPL application with Claude Code TUI."""
from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static, Markdown
from textual.worker import Worker

from app.commands.bash_exec import execute_bash
from app.components.command_suggestions import CommandSuggestions
from app.components.logo_header import LogoHeader
from app.components.messages import Messages
from app.components.permission_prompt import PermissionPrompt
from app.components.prompt_input import PromptInput
from app.components.spinner import Spinner
from app.components.status_bar import StatusBar
from app.input_modes import InputMode, strip_mode_prefix
from app.query import QueryResult
from app.query_engine import QueryEngine
from app.state.app_state import AppState
from app.themes.claude_theme import (
    BACKGROUND,
    SURFACE,
    SURFACE_LIGHT,
    CLAUDE_ORANGE,
    TEXT,
    TEXT_MUTED,
    TEXT_SUBTLE,
    BORDER_NORMAL,
    BORDER_FOCUSED,
)
from app.types.permissions import PermissionResult


class ClaudeCodeApp(App):
    """Interactive REPL for Claude Code — fullscreen TUI."""

    TITLE = "Claude Code"

    CSS = f"""
    Screen {{
        background: {BACKGROUND};
    }}

    /* ── Logo header ─────────────────────────────────── */
    #logo {{
        dock: top;
        height: auto;
        background: {BACKGROUND};
    }}

    /* ── Divider below header ────────────────────────── */
    #header-divider {{
        dock: top;
        height: 1;
        background: {SURFACE_LIGHT};
        color: {TEXT_SUBTLE};
        padding: 0 2;
    }}

    /* ── Messages area ───────────────────────────────── */
    #messages {{
        height: 1fr;
        background: {BACKGROUND};
        scrollbar-size: 1 1;
    }}
    #messages Markdown {{
        margin: 0 0 1 0;
        padding: 0 1;
    }}

    /* ── Spinner ──────────────────────────────────────── */
    #spinner {{
        dock: bottom;
        background: {BACKGROUND};
    }}

    /* ── Permission prompt ────────────────────────────── */
    #permission {{
        dock: bottom;
    }}

    /* ── Command suggestions ──────────────────────────── */
    #suggestions {{
        dock: bottom;
        background: {SURFACE};
        border: tall {TEXT_SUBTLE};
        padding: 0 1;
        margin-bottom: 0;
        max-height: 12;
    }}

    /* ── Status bar ───────────────────────────────────── */
    #status-bar {{
        dock: bottom;
        height: 1;
        background: {SURFACE};
    }}

    /* ── Input area ───────────────────────────────────── */
    #input {{
        dock: bottom;
        min-height: 3;
        max-height: 12;
        border: tall {BORDER_NORMAL};
        background: {SURFACE};
        padding: 0 0;
    }}
    #input:focus {{
        border: tall {BORDER_FOCUSED};
    }}

    /* ── Keybinding hints ─────────────────────────────── */
    #hints {{
        dock: bottom;
        height: 1;
        background: {SURFACE};
        color: {TEXT_SUBTLE};
        padding: 0 1;
    }}
    """

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit", show=False),
        Binding("ctrl+l", "clear_screen", "Clear", show=False),
    ]

    def __init__(
        self, engine: QueryEngine, state: AppState, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.engine = engine
        self.state = state
        self._current_worker: Worker | None = None
        self._permission_event: asyncio.Event | None = None
        self._permission_result: PermissionResult | None = None
        # Wire app_state reference into engine for command context
        self.engine._app_state = state

    def compose(self) -> ComposeResult:
        yield LogoHeader(
            version="0.1.0",
            model=self.state.model,
            cwd=self.state.cwd,
            id="logo",
        )
        yield Static(
            "─" * 80,
            id="header-divider",
        )
        yield Messages(id="messages")
        yield Spinner(id="spinner")
        yield PermissionPrompt(id="permission")
        yield CommandSuggestions(id="suggestions")
        yield StatusBar(id="status-bar")
        yield PromptInput(history=self.state.input_history, id="input")
        yield Static(
            " Ctrl+D quit │ Ctrl+L clear │ Shift+Tab mode │ /help commands │ Esc cancel",
            id="hints",
        )

    def on_mount(self) -> None:
        """Focus the input on start and initialize status bar."""
        self.query_one("#input", PromptInput).focus()
        self._update_status()

    # ── Event handlers ────────────────────────────────────────────────

    def on_prompt_input_user_submitted(self, event: PromptInput.UserSubmitted) -> None:
        """Handle user input submission."""
        text = event.text
        if not text:
            return

        self.state.is_busy = True
        prompt_input = self.query_one("#input", PromptInput)
        prompt_input.disabled = True

        messages = self.query_one("#messages", Messages)
        spinner = self.query_one("#spinner", Spinner)

        if event.mode == InputMode.BASH:
            command = strip_mode_prefix(text, InputMode.BASH)
            messages.append_user(f"!{command}")
            spinner.show("Running command")
            self._current_worker = self.run_worker(
                self._run_bash(command), thread=False, exclusive=True
            )
        else:
            messages.append_user(text)
            spinner.show("Thinking")
            self._current_worker = self.run_worker(
                self._run_query(text), thread=False, exclusive=True
            )

    def on_prompt_input_cancel_requested(
        self, event: PromptInput.CancelRequested
    ) -> None:
        """Handle Escape — cancel running query."""
        if self._current_worker and self._current_worker.is_running:
            self._current_worker.cancel()
            self.state.is_busy = False
            messages = self.query_one("#messages", Messages)
            messages.finalize_assistant()
            messages.append_system("Query cancelled.")
            self.query_one("#spinner", Spinner).hide()
            self._enable_input()

    def on_prompt_input_mode_changed(self, event: PromptInput.ModeChanged) -> None:
        """Update status bar when input mode changes."""
        self._update_status()

    def on_prompt_input_command_input_changed(self, event: PromptInput.CommandInputChanged) -> None:
        """Show/update command suggestions when user types a slash command prefix."""
        suggestions = self.query_one("#suggestions", CommandSuggestions)
        prompt_input = self.query_one("#input", PromptInput)
        commands = self.engine.command_registry.list_commands()
        prefix = event.prefix.lower()
        matches = [
            (cmd.name, cmd.description)
            for cmd in commands
            if cmd.name.startswith(prefix)
        ]
        suggestions.update_suggestions(matches)
        prompt_input.suggesting = bool(matches)

    def on_prompt_input_command_input_cleared(self, event: PromptInput.CommandInputCleared) -> None:
        """Hide command suggestions."""
        self.query_one("#suggestions", CommandSuggestions).hide()

    def on_prompt_input_suggestion_navigate(self, event: PromptInput.SuggestionNavigate) -> None:
        """Move selection in command suggestions."""
        self.query_one("#suggestions", CommandSuggestions).move_selection(event.delta)

    def on_prompt_input_suggestion_confirm(self, event: PromptInput.SuggestionConfirm) -> None:
        """Confirm the selected command suggestion."""
        suggestions = self.query_one("#suggestions", CommandSuggestions)
        prompt_input = self.query_one("#input", PromptInput)
        name = suggestions.confirm_selection()
        if name:
            prompt_input.value = f"/{name} "
            prompt_input.suggesting = False

    def on_permission_prompt_resolved(
        self, event: PermissionPrompt.Resolved
    ) -> None:
        """Handle permission dialog response."""
        self._permission_result = event.result
        if self._permission_event:
            self._permission_event.set()

    # ── Actions ───────────────────────────────────────────────────────

    def action_clear_screen(self) -> None:
        """Clear messages and reset session."""
        self.engine.clear()
        self.query_one("#messages", Messages).clear_messages()
        self.state.turn_count = 0
        self.state.total_input_tokens = 0
        self.state.total_output_tokens = 0
        self._update_status()

    # ── Internal methods ──────────────────────────────────────────────

    async def _run_bash(self, command: str) -> None:
        """Execute a bash command directly and display the result."""
        messages = self.query_one("#messages", Messages)
        spinner = self.query_one("#spinner", Spinner)
        try:
            result = await execute_bash(command, self.state.cwd)
            messages.append_system(result.text)
        except asyncio.CancelledError:
            messages.append_system("Command cancelled.")
        except Exception as e:
            messages.append_system(f"Error: {e}")
        finally:
            self.state.is_busy = False
            spinner.hide()
            self._enable_input()

    async def _run_query(self, text: str) -> None:
        """Execute a query turn with streaming callbacks."""
        messages = self.query_one("#messages", Messages)
        spinner = self.query_one("#spinner", Spinner)

        def on_text(chunk: str) -> None:
            # Once we start getting text, switch spinner to indicate streaming
            spinner.update_verb("Generating")
            messages.append_assistant_chunk(chunk)

        def on_tool_use(name: str, tool_input: dict) -> None:
            spinner.update_verb(f"Running {name}")
            messages.append_tool_call(name, tool_input)

        try:
            result = await self.engine.run_turn(
                text, on_text=on_text, on_tool_use=on_tool_use
            )
            messages.finalize_assistant()

            # Handle command result displayed as system message (slash commands)
            if result.response_text and not result.tool_calls:
                from app.commands import is_command
                if is_command(text):
                    messages.append_system(result.response_text)

            # Show tool results from the query result
            for tc in result.tool_calls:
                tool_result = tc.get("result")
                if tool_result:
                    content = (
                        tool_result.content
                        if isinstance(tool_result.content, str)
                        else str(tool_result.content)
                    )
                    messages.append_tool_result(
                        tc["tool_name"], content, tool_result.is_error
                    )

            # Handle exit request from commands like /exit
            if getattr(result, "should_exit", False):
                self.exit()

        except asyncio.CancelledError:
            messages.finalize_assistant()
            messages.append_system("Query cancelled.")
        except Exception as e:
            messages.finalize_assistant()
            messages.append_system(f"Error: {e}")
        finally:
            self.state.is_busy = False
            self.state.turn_count = self.engine.turn_count
            self.state.total_input_tokens = self.engine.total_input_tokens
            self.state.total_output_tokens = self.engine.total_output_tokens
            spinner.hide()
            self._update_status()
            self._enable_input()

    async def permission_callback(
        self, tool_name: str, tool_input: dict
    ) -> PermissionResult:
        """Called by ToolExecutor when ASK_USER permission is needed."""
        self._permission_event = asyncio.Event()
        self._permission_result = None

        prompt = self.query_one("#permission", PermissionPrompt)
        prompt.show_prompt(tool_name, tool_input)

        # Wait for user to click a button
        await self._permission_event.wait()

        prompt.hide_prompt()
        return self._permission_result or PermissionResult.DENY

    def _enable_input(self) -> None:
        """Re-enable and focus the input widget."""
        prompt_input = self.query_one("#input", PromptInput)
        prompt_input.disabled = False
        prompt_input.focus()

    def _update_status(self) -> None:
        """Update the status bar with current state."""
        input_mode = "prompt"
        try:
            prompt_input = self.query_one("#input", PromptInput)
            if prompt_input.input_mode == InputMode.BASH:
                input_mode = "bash"
        except Exception:
            pass

        # Calculate context percentage
        context_pct = 0.0
        total_tokens = self.state.total_input_tokens + self.state.total_output_tokens
        if total_tokens > 0:
            # Rough estimate: model context window
            max_ctx = 200000  # default for Claude models
            context_pct = min(100.0, (total_tokens / max_ctx) * 100)

        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_state(
            model=self.state.model,
            permission_mode=self.state.permission_mode,
            input_tokens=self.state.total_input_tokens,
            output_tokens=self.state.total_output_tokens,
            context_pct=context_pct,
            cwd=self.state.cwd,
            input_mode=input_mode,
        )
