"""PromptInput widget — multiline user input with history, keyboard shortcuts, and input modes."""
from __future__ import annotations

from textual.message import Message
from textual.widgets import TextArea
from textual.events import Key

from app.input_modes import InputMode, detect_mode, strip_mode_prefix, prepend_mode_prefix
from app.themes.claude_theme import CLAUDE_ORANGE

_PLACEHOLDERS = {
    InputMode.PROMPT: "Type a message… (Enter to send, Shift+Enter for newline)",
    InputMode.BASH: "! Shell command…",
}


class PromptInput(TextArea):
    """Multiline input widget with submit, history navigation, mode switching, and cancel support."""

    DEFAULT_CSS = """
    PromptInput {
        dock: bottom;
        height: auto;
        min-height: 3;
        max-height: 12;
        border: tall $accent;
        padding: 0 0;
    }
    PromptInput:focus {
        border: tall #d77757;
    }
    """

    class UserSubmitted(Message):
        """Posted when user presses Enter with non-empty text."""

        def __init__(self, text: str, mode: InputMode = InputMode.PROMPT) -> None:
            super().__init__()
            self.text = text
            self.mode = mode

    class CancelRequested(Message):
        """Posted when user presses Escape to cancel a running query."""
        pass

    class ModeChanged(Message):
        """Posted when the input mode changes."""

        def __init__(self, mode: InputMode) -> None:
            super().__init__()
            self.mode = mode

    class CommandInputChanged(Message):
        """Posted when the input looks like a slash command prefix."""

        def __init__(self, prefix: str) -> None:
            super().__init__()
            self.prefix = prefix

    class CommandInputCleared(Message):
        """Posted when the input no longer looks like a slash command."""
        pass

    class SuggestionNavigate(Message):
        """Posted when user presses up/down while suggestions are visible."""

        def __init__(self, delta: int) -> None:
            super().__init__()
            self.delta = delta

    class SuggestionConfirm(Message):
        """Posted when user presses Tab to confirm a suggestion."""
        pass

    def __init__(self, history: list[str] | None = None, **kwargs) -> None:
        # Remove 'placeholder' if passed — TextArea doesn't take it the same way
        kwargs.pop("placeholder", None)
        super().__init__(**kwargs)
        self._history: list[str] = history or []
        self._history_index: int = -1
        self._draft: str = ""
        self._input_mode: InputMode = InputMode.PROMPT
        self._suggesting: bool = False

    @property
    def input_mode(self) -> InputMode:
        return self._input_mode

    @property
    def suggesting(self) -> bool:
        return self._suggesting

    @suggesting.setter
    def suggesting(self, value: bool) -> None:
        self._suggesting = value

    @property
    def value(self) -> str:
        """Get the text content (compatibility with old Input API)."""
        return self.text

    @value.setter
    def value(self, new_text: str) -> None:
        """Set the text content (compatibility with old Input API)."""
        self.clear()
        self.insert(new_text)

    def _on_key(self, event: Key) -> None:
        """Handle special keys before default TextArea behavior."""
        # Suggestion navigation takes priority
        if self._suggesting:
            if event.key == "up":
                self.post_message(self.SuggestionNavigate(-1))
                event.prevent_default()
                return
            elif event.key == "down":
                self.post_message(self.SuggestionNavigate(1))
                event.prevent_default()
                return
            elif event.key == "tab":
                self.post_message(self.SuggestionConfirm())
                event.prevent_default()
                return
            elif event.key == "escape":
                self._suggesting = False
                self.post_message(self.CommandInputCleared())
                event.prevent_default()
                return

        # Enter = submit (without shift)
        if event.key == "enter":
            self._submit()
            event.prevent_default()
            return

        # Shift+Enter = newline (handled by default TextArea, no override needed)

        # History navigation (only when single-line or cursor at top/bottom)
        if event.key == "up" and self._cursor_at_start():
            self._navigate_history(-1)
            event.prevent_default()
            return
        elif event.key == "down" and self._cursor_at_end():
            self._navigate_history(1)
            event.prevent_default()
            return

        if event.key == "escape":
            self.post_message(self.CancelRequested())
            event.prevent_default()
            return

        if event.key == "shift+tab":
            self._cycle_mode()
            event.prevent_default()
            return

    def _on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Detect slash command prefix and emit suggestion events."""
        value = self.text.strip()
        if value.startswith("/") and " " not in value and "\n" not in value:
            prefix = value[1:]
            self._suggesting = True
            self.post_message(self.CommandInputChanged(prefix))
        elif self._suggesting:
            self._suggesting = False
            self.post_message(self.CommandInputCleared())

    def _submit(self) -> None:
        """Submit the current input text."""
        # Hide suggestions on submit
        if self._suggesting:
            self._suggesting = False
            self.post_message(self.CommandInputCleared())

        text = self.text.strip()
        if not text:
            return

        # Detect mode from text content
        mode = detect_mode(text)

        # Save to history
        if not self._history or self._history[-1] != text:
            self._history.append(text)
        self._history_index = -1
        self._draft = ""

        # Clear input
        self.clear()

        # Reset mode to PROMPT after submission
        if self._input_mode != InputMode.PROMPT:
            self._input_mode = InputMode.PROMPT

        self.post_message(self.UserSubmitted(text, mode))

    def _cycle_mode(self) -> None:
        """Cycle between PROMPT and BASH input modes."""
        if self._input_mode == InputMode.PROMPT:
            new_mode = InputMode.BASH
            current = self.text.strip()
            if current and not current.startswith("!"):
                self.value = f"!{current}"
            elif not current:
                self.value = "!"
        else:
            new_mode = InputMode.PROMPT
            current = self.text.strip()
            if current.startswith("!"):
                self.value = current[1:].strip()

        self._input_mode = new_mode
        self.post_message(self.ModeChanged(new_mode))

    def _navigate_history(self, direction: int) -> None:
        """Navigate input history with up/down arrows."""
        if not self._history:
            return

        if self._history_index == -1:
            self._draft = self.text

        new_index = self._history_index + direction

        if new_index < -1:
            new_index = -1
        elif new_index >= len(self._history):
            new_index = len(self._history) - 1

        if new_index == -1:
            self.value = self._draft
            self._history_index = -1
        else:
            self._history_index = new_index
            idx = len(self._history) - 1 - new_index
            if 0 <= idx < len(self._history):
                self.value = self._history[idx]

    def _cursor_at_start(self) -> bool:
        """Check if cursor is at the first line."""
        row, _ = self.cursor_location
        return row == 0

    def _cursor_at_end(self) -> bool:
        """Check if cursor is at the last line."""
        row, _ = self.cursor_location
        return row >= self.document.line_count - 1
