"""PromptInput widget — user input with history and keyboard shortcuts."""
from __future__ import annotations

from textual.message import Message
from textual.widgets import Input


class PromptInput(Input):
    """Input widget with submit, history navigation, and cancel support."""

    DEFAULT_CSS = """
    PromptInput {
        dock: bottom;
        height: 3;
        border: tall $accent;
    }
    """

    class UserSubmitted(Message):
        """Posted when user presses Enter with non-empty text."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class CancelRequested(Message):
        """Posted when user presses Escape to cancel a running query."""
        pass

    def __init__(self, history: list[str] | None = None, **kwargs) -> None:
        super().__init__(placeholder="Type a message...", **kwargs)
        self._history: list[str] = history or []
        self._history_index: int = -1
        self._draft: str = ""

    def _on_key(self, event) -> None:
        """Handle special keys."""
        if event.key == "up":
            self._navigate_history(-1)
            event.prevent_default()
        elif event.key == "down":
            self._navigate_history(1)
            event.prevent_default()
        elif event.key == "escape":
            self.post_message(self.CancelRequested())
            event.prevent_default()

    def _on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key — intercept the base Input.Submitted."""
        event.stop()
        text = self.value.strip()
        if not text:
            return

        # Save to history
        if not self._history or self._history[-1] != text:
            self._history.append(text)
        self._history_index = -1
        self._draft = ""

        # Clear input and post our UserSubmitted message
        self.value = ""
        self.post_message(self.UserSubmitted(text))

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
