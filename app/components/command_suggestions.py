"""Command suggestions dropdown for slash command autocomplete."""
from __future__ import annotations

from textual.widget import Widget
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text


class CommandSuggestions(Widget):
    """Dropdown widget showing matching slash commands."""

    DEFAULT_CSS = """
    CommandSuggestions {
        dock: bottom;
        height: auto;
        max-height: 12;
        display: none;
        background: $surface;
        border: tall $accent;
        padding: 0 1;
        margin-bottom: 3;
    }
    CommandSuggestions.visible {
        display: block;
    }
    """

    selected_index: reactive[int] = reactive(0)

    class CommandSelected(Message):
        """Posted when a command is selected from suggestions."""

        def __init__(self, command_name: str) -> None:
            super().__init__()
            self.command_name = command_name

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items: list[tuple[str, str]] = []  # (name, description)

    def update_suggestions(self, items: list[tuple[str, str]]) -> None:
        """Update the displayed suggestions list."""
        self._items = items
        self.selected_index = 0
        if items:
            self.add_class("visible")
        else:
            self.remove_class("visible")
        self.refresh()

    def hide(self) -> None:
        """Hide the suggestions dropdown."""
        self._items = []
        self.remove_class("visible")
        self.refresh()

    def move_selection(self, delta: int) -> None:
        """Move the selection cursor by delta."""
        if not self._items:
            return
        self.selected_index = (self.selected_index + delta) % len(self._items)
        self.refresh()

    def confirm_selection(self) -> str | None:
        """Confirm the current selection. Returns the command name or None."""
        if not self._items or self.selected_index >= len(self._items):
            return None
        name = self._items[self.selected_index][0]
        self.hide()
        return name

    @property
    def is_visible(self) -> bool:
        return self.has_class("visible")

    def render(self) -> Text:
        lines = Text()
        for i, (name, desc) in enumerate(self._items):
            prefix = " > " if i == self.selected_index else "   "
            line = Text(f"{prefix}/{name}")
            if i == self.selected_index:
                line.stylize("bold reverse")
            line.append(f"  {desc}", style="dim")
            if i < len(self._items) - 1:
                line.append("\n")
            lines.append(line)
        return lines
