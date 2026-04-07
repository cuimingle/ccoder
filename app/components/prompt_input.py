"""PromptInput widget — user input with history, keyboard shortcuts, and input modes."""
from __future__ import annotations

from textual.message import Message
from textual.widgets import Input

from app.input_modes import InputMode, detect_mode, strip_mode_prefix, prepend_mode_prefix

_PLACEHOLDERS = {
    InputMode.PROMPT: "Type a message...",
    InputMode.BASH: "! Shell command...",
}


class PromptInput(Input):
    """Input widget with submit, history navigation, mode switching, and cancel support."""

    DEFAULT_CSS = """
    PromptInput {
        dock: bottom;
        height: 3;
        border: tall $accent;
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
        super().__init__(placeholder=_PLACEHOLDERS[InputMode.PROMPT], **kwargs)
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

    def _on_key(self, event) -> None:
        """Handle special keys."""
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

        if event.key == "up":
            self._navigate_history(-1)
            event.prevent_default()
        elif event.key == "down":
            self._navigate_history(1)
            event.prevent_default()
        elif event.key == "escape":
            self.post_message(self.CancelRequested())
            event.prevent_default()
        elif event.key == "shift+tab":
            self._cycle_mode()
            event.prevent_default()

    def _on_input_changed(self, event: Input.Changed) -> None:
        """Detect slash command prefix and emit suggestion events."""
        value = event.value.strip()
        if value.startswith("/") and " " not in value:
            prefix = value[1:]
            self._suggesting = True
            self.post_message(self.CommandInputChanged(prefix))
        elif self._suggesting:
            self._suggesting = False
            self.post_message(self.CommandInputCleared())

    def _cycle_mode(self) -> None:
        """Cycle between PROMPT and BASH input modes."""
        if self._input_mode == InputMode.PROMPT:
            new_mode = InputMode.BASH
            # Prepend ! to current text
            current = self.value.strip()
            if current and not current.startswith("!"):
                self.value = f"!{current}"
            elif not current:
                self.value = "!"
        else:
            new_mode = InputMode.PROMPT
            # Strip ! prefix from current text
            current = self.value.strip()
            if current.startswith("!"):
                self.value = current[1:].strip()

        self._input_mode = new_mode
        self.placeholder = _PLACEHOLDERS[new_mode]
        self.post_message(self.ModeChanged(new_mode))

    def _on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key — intercept the base Input.Submitted."""
        event.stop()

        # Hide suggestions on submit
        if self._suggesting:
            self._suggesting = False
            self.post_message(self.CommandInputCleared())

        text = self.value.strip()
        if not text:
            return

        # Detect mode from text content
        mode = detect_mode(text)

        # Save to history
        if not self._history or self._history[-1] != text:
            self._history.append(text)
        self._history_index = -1
        self._draft = ""

        # Clear input and post our UserSubmitted message
        self.value = ""

        # Reset mode to PROMPT after submission
        if self._input_mode != InputMode.PROMPT:
            self._input_mode = InputMode.PROMPT
            self.placeholder = _PLACEHOLDERS[InputMode.PROMPT]

        self.post_message(self.UserSubmitted(text, mode))

    def _navigate_history(self, direction: int) -> None:
        """Navigate input history with up/down arrows."""
        if not self._history:
            return

        if self._history_index == -1:
            self._draft = self.value

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
