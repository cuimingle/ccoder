"""ClaudeCodeApp — main Textual REPL application."""
from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static
from textual.worker import Worker

from app.commands.bash_exec import execute_bash
from app.components.command_suggestions import CommandSuggestions
from app.components.messages import Messages
from app.components.permission_prompt import PermissionPrompt
from app.components.prompt_input import PromptInput
from app.input_modes import InputMode, strip_mode_prefix
from app.query import QueryResult
from app.query_engine import QueryEngine
from app.state.app_state import AppState
from app.types.permissions import PermissionResult


class ClaudeCodeApp(App):
    """Interactive REPL for Claude Code."""

    TITLE = "Claude Code"

    CSS = """
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_screen", "Clear", show=True),
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
        yield Header(show_clock=False)
        yield Messages(id="messages")
        yield PermissionPrompt(id="permission")
        yield CommandSuggestions(id="suggestions")
        yield Static(self._status_text(), id="status-bar")
        yield PromptInput(history=self.state.input_history, id="input")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the input on start."""
        self.query_one("#input", PromptInput).focus()

    # --- Event handlers ---

    def on_prompt_input_user_submitted(self, event: PromptInput.UserSubmitted) -> None:
        """Handle user input submission."""
        text = event.text
        if not text:
            return

        self.state.is_busy = True
        prompt_input = self.query_one("#input", PromptInput)
        prompt_input.disabled = True

        messages = self.query_one("#messages", Messages)

        if event.mode == InputMode.BASH:
            # Direct shell execution — bypass Claude API
            command = strip_mode_prefix(text, InputMode.BASH)
            messages.append_user(f"!{command}")
            self._current_worker = self.run_worker(
                self._run_bash(command), thread=False, exclusive=True
            )
        else:
            # Normal prompt or slash command
            messages.append_user(text)
            self._current_worker = self.run_worker(
                self._run_query(text), thread=False, exclusive=True
            )

    def on_prompt_input_cancel_requested(
        self, event: PromptInput.CancelRequested
    ) -> None:
        """Handle Ctrl+C / Escape — cancel running query."""
        if self._current_worker and self._current_worker.is_running:
            self._current_worker.cancel()
            self.state.is_busy = False
            messages = self.query_one("#messages", Messages)
            messages.finalize_assistant()
            messages.append_system("Query cancelled.")
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

    # --- Actions ---

    def action_clear_screen(self) -> None:
        """Clear messages and reset session."""
        self.engine.clear()
        self.query_one("#messages", Messages).clear_messages()
        self.state.turn_count = 0
        self.state.total_input_tokens = 0
        self.state.total_output_tokens = 0
        self._update_status()

    # --- Internal methods ---

    async def _run_bash(self, command: str) -> None:
        """Execute a bash command directly and display the result."""
        messages = self.query_one("#messages", Messages)
        try:
            result = await execute_bash(command, self.state.cwd)
            messages.append_system(result.text)
        except asyncio.CancelledError:
            messages.append_system("Command cancelled.")
        except Exception as e:
            messages.append_system(f"Error: {e}")
        finally:
            self.state.is_busy = False
            self._enable_input()

    async def _run_query(self, text: str) -> None:
        """Execute a query turn with streaming callbacks."""
        messages = self.query_one("#messages", Messages)

        def on_text(chunk: str) -> None:
            messages.append_assistant_chunk(chunk)

        def on_tool_use(name: str, tool_input: dict) -> None:
            messages.append_tool_call(name, tool_input)

        try:
            result = await self.engine.run_turn(
                text, on_text=on_text, on_tool_use=on_tool_use
            )
            messages.finalize_assistant()

            # Handle command result displayed as system message (slash commands)
            if result.response_text and not result.tool_calls:
                # Only show as system message if it came from a slash command
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

    def _status_text(self) -> str:
        """Build status bar text."""
        model = self.state.model
        in_t = self.state.total_input_tokens
        out_t = self.state.total_output_tokens

        # Show input mode indicator
        mode_str = ""
        try:
            prompt_input = self.query_one("#input", PromptInput)
            if prompt_input.input_mode == InputMode.BASH:
                mode_str = " [BASH] |"
        except Exception:
            pass

        return f" {model} |{mode_str} In: {in_t:,} Out: {out_t:,} | {self.state.cwd}"

    def _update_status(self) -> None:
        """Update the status bar."""
        self.query_one("#status-bar", Static).update(self._status_text())
