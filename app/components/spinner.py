"""Spinner widget — animated progress indicator for API calls and tool execution."""
from __future__ import annotations

from rich.text import Text
from textual.widget import Widget
from textual.timer import Timer

from app.themes.claude_theme import CLAUDE_ORANGE, CLAUDE_ORANGE_SHIMMER, TEXT_MUTED

# Braille spinner frames (smooth rotation)
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Teardrop asterisk for idle
TEARDROP = "✺"


class Spinner(Widget):
    """Animated spinner with descriptive verb text."""

    DEFAULT_CSS = """
    Spinner {
        height: 1;
        padding: 0 2;
        display: none;
    }
    Spinner.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._frame_index: int = 0
        self._verb: str = "Thinking"
        self._detail: str = ""
        self._timer: Timer | None = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.12, self._advance_frame)

    def _advance_frame(self) -> None:
        if self.has_class("visible"):
            self._frame_index = (self._frame_index + 1) % len(SPINNER_FRAMES)
            self.refresh()

    def show(self, verb: str = "Thinking", detail: str = "") -> None:
        """Show spinner with given verb text."""
        self._verb = verb
        self._detail = detail
        self._frame_index = 0
        self.add_class("visible")

    def hide(self) -> None:
        """Hide the spinner."""
        self.remove_class("visible")

    def update_verb(self, verb: str, detail: str = "") -> None:
        """Update the displayed verb and optional detail text."""
        self._verb = verb
        self._detail = detail
        self.refresh()

    def render(self) -> Text:
        frame = SPINNER_FRAMES[self._frame_index]
        output = Text()
        output.append(f" {frame} ", style=f"bold {CLAUDE_ORANGE}")
        output.append(f"{self._verb}…", style=f"bold {CLAUDE_ORANGE_SHIMMER}")
        if self._detail:
            output.append(f"  {self._detail}", style=f"{TEXT_MUTED}")
        return output
